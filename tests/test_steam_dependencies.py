"""Offline native-boundary tests for optional Workshop dependency operations."""

import ctypes
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock

ROOT = next(path for path in Path(__file__).resolve().parents if (path / 'tools/mod_cli.py').is_file())
VARIANT = os.environ.get('RIMWORLD_TEST_VARIANT')
SKILLS = Path(VARIANT) if VARIANT else ROOT / 'skills'
if not SKILLS.is_dir() and not VARIANT:
    SKILLS = ROOT / 'basic/skills'
sys.path.insert(0, str(SKILLS / 'rimworld-publish/scripts'))
import steam_backend as steam


ITEM = 9_200_001
CHILD = 9_200_002
APP = 1_826_140
CALL = (1 << 56) | 42
QUERY = 130


class SteamDependencyTests(unittest.TestCase):
    def setUp(self):
        self.backend = steam.SteamworksUGC(Path('offline-sdk'))
        self.backend._ugc = 17
        self.backend._types = steam._abi(8)
        self.backend._lib = Mock(spec=[
            'SteamAPI_ISteamUGC_' + name for name in (
                'AddDependency', 'AddAppDependency', 'SetReturnChildren', 'GetQueryUGCChildren',
                'GetAppDependencies', 'CreateQueryUGCDetailsRequest', 'SetAllowCachedResponse',
                'SendQueryUGCRequest', 'GetQueryUGCResult', 'ReleaseQueryUGCRequest',
            )
        ])
        self.library = self.backend._lib

    def test_callback_layouts_match_sdk_packing(self):
        for pack, sizes in ((4, (20, 16, 148)), (8, (24, 24, 152))):
            with self.subTest(pack=pack):
                layouts = steam._abi(pack)
                for name, size in zip(('add_dependency', 'add_app_dependency', 'app_dependencies'), sizes):
                    self.assertEqual(ctypes.sizeof(layouts[name]), size)
                    self.assertEqual(layouts[name].file_id.offset, pack)
                self.assertEqual(layouts['app_dependencies'].returned.offset, 136 + pack)
                self.assertEqual(layouts['app_dependencies'].total.offset, 140 + pack)
        self.assertEqual(steam._abi(8)['details'].child_count.offset, 9768)

    def test_add_uses_parent_id_and_waits_for_independent_64_bit_call(self):
        item_payload = struct.pack('<i4xQQ', 1, ITEM, CHILD)
        app_payload = struct.pack('<i4xQI4x', 1, ITEM, APP)
        self.library.SteamAPI_ISteamUGC_AddDependency.return_value = CALL
        self.library.SteamAPI_ISteamUGC_AddAppDependency.return_value = CALL
        self.backend._wait_apicall = Mock(side_effect=[
            self.backend._types['add_dependency'].from_buffer_copy(item_payload),
            self.backend._types['add_app_dependency'].from_buffer_copy(app_payload),
        ])
        self.backend.add_dependency(ITEM, CHILD)
        self.backend.add_app_dependency(ITEM, APP)
        self.library.SteamAPI_ISteamUGC_AddDependency.assert_called_once_with(17, ITEM, CHILD)
        self.library.SteamAPI_ISteamUGC_AddAppDependency.assert_called_once_with(17, ITEM, APP)
        for name in ('AddDependency', 'AddAppDependency'):
            self.assertIs(getattr(self.library, 'SteamAPI_ISteamUGC_' + name).restype, ctypes.c_uint64)
        waits = self.backend._wait_apicall.call_args_list
        self.assertEqual([wait.args[:2] for wait in waits], [(CALL, 3412), (CALL, 3414)])
        self.assertTrue(all(wait.kwargs == {'mutation': True} for wait in waits))

    def test_callback_identity_mismatch_is_unknown(self):
        self.backend._wait_apicall = Mock(
            return_value=self.backend._types['add_dependency'](1, ITEM, CHILD + 1))
        with self.assertRaises(steam.SteamworksError) as failed:
            self.backend.add_dependency(ITEM, CHILD)
        self.assertTrue(failed.exception.outcome_unknown)

    def test_matching_callback_can_report_known_failure(self):
        self.backend._wait_apicall = Mock(
            return_value=self.backend._types['add_app_dependency'](15, ITEM, APP))
        with self.assertRaises(steam.SteamworksError) as failed:
            self.backend.add_app_dependency(ITEM, APP)
        self.assertFalse(failed.exception.outcome_unknown)
        self.assertEqual(failed.exception.result_code, 15)

    def _set_queries(self, *, child_count=2, app_count=1, app_total=1, item_id=ITEM):
        self.library.SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest.return_value = QUERY
        self.library.SteamAPI_ISteamUGC_SendQueryUGCRequest.return_value = CALL
        self.library.SteamAPI_ISteamUGC_GetAppDependencies.return_value = CALL + 1

        def detail(_ugc, _query, _index, output):
            record = self.backend._types['details'](file_id=item_id, result=1,
                                                   consumer_app_id=steam.APPID, child_count=child_count)
            ctypes.memmove(output, ctypes.byref(record), ctypes.sizeof(record))
            return True

        def children(_ugc, _query, _index, output, count):
            self.assertEqual(count, child_count)
            output[0], output[1] = CHILD, CHILD + 1
            return True

        self.library.SteamAPI_ISteamUGC_GetQueryUGCResult.side_effect = detail
        self.library.SteamAPI_ISteamUGC_GetQueryUGCChildren.side_effect = children
        payload = struct.pack('<i4xQ32III', 1, ITEM, APP, *[0] * 31, app_count, app_total)
        self.backend._wait_apicall = Mock(side_effect=[
            self.backend._types['query'](QUERY, 1, 1, 1),
            self.backend._types['app_dependencies'].from_buffer_copy(payload),
        ])

    def test_reads_exact_child_count_and_full_app_page(self):
        self._set_queries()
        self.assertEqual(self.backend.query_dependencies(ITEM), {'items': [CHILD, CHILD + 1], 'apps': [APP]})
        self.library.SteamAPI_ISteamUGC_SetReturnChildren.assert_called_once_with(17, QUERY, True)
        self.library.SteamAPI_ISteamUGC_SetAllowCachedResponse.assert_called_once_with(17, QUERY, 0)
        self.library.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest.assert_called_once_with(17, QUERY)
        self.library.SteamAPI_ISteamUGC_AddDependency.assert_not_called()
        self.library.SteamAPI_ISteamUGC_AddAppDependency.assert_not_called()

    def test_partial_app_page_cannot_certify_absence(self):
        self._set_queries(app_total=2)
        with self.assertRaisesRegex(steam.SteamworksError, '1/2'):
            self.backend.query_dependencies(ITEM)

    def test_wrong_parent_from_query_is_rejected_and_released(self):
        self._set_queries(item_id=ITEM + 1)
        with self.assertRaises(steam.SteamworksError):
            self.backend.query_dependencies(ITEM)
        self.library.SteamAPI_ISteamUGC_GetQueryUGCChildren.assert_not_called()
        self.library.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest.assert_called_once_with(17, QUERY)

    def test_failed_children_read_is_not_an_empty_result(self):
        self._set_queries()
        self.library.SteamAPI_ISteamUGC_GetQueryUGCChildren.side_effect = None
        self.library.SteamAPI_ISteamUGC_GetQueryUGCChildren.return_value = False
        with self.assertRaisesRegex(steam.SteamworksError, 'GetQueryUGCChildren'):
            self.backend.query_dependencies(ITEM)
        self.library.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest.assert_called_once_with(17, QUERY)


if __name__ == '__main__':
    unittest.main()
