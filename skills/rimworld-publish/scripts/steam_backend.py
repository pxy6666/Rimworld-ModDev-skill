"""Steamworks UGC adapter for the desktop Steam session; no game process required."""

import ctypes as C
import os
import platform
import re
import struct
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, ExitStack
from pathlib import Path
from xml.etree import ElementTree as ET

APPID = 294100
DEFAULT_RUN_DIR = Path.home() / '.rimworld-publish' / 'steamworks'
DYLIB_ENV = 'RIMWORLD_STEAM_DYLIB'
_MAX_HANDLE = (1 << 64) - 1
_APP_ENV = ('SteamAppId', 'SteamGameId', 'SteamOverlayGameId')
_SESSION = threading.Lock()  # cwd and the native Steam API are process-global

# Valve: https://partner.steamgames.com/doc/api/steam_api#EResult
_ERESULT = {2: 'Fail', 3: 'NoConnection', 8: 'InvalidParam', 9: 'FileNotFound',
            10: 'Busy', 11: 'InvalidState', 14: 'DuplicateName', 15: 'AccessDenied',
            16: 'Timeout', 17: 'Banned', 18: 'AccountNotFound', 20: 'ServiceUnavailable',
            21: 'NotLoggedOn', 22: 'Pending', 24: 'InsufficientPrivilege',
            25: 'LimitExceeded', 29: 'DuplicateRequest', 32: 'PersistFailed', 37: 'IOFailure',
            38: 'RemoteDisconnect', 43: 'AccountDisabled', 44: 'ServiceReadOnly',
            45: 'AccountNotFeatured', 84: 'RateLimitExceeded'}
# Only clear input, permission, quota or client-state rejections are known not
# to have applied this mutation. I/O, generic, duplicate and unknown results
# require reconciliation before an external write may be attempted again.
_DEFINITE_REJECTIONS = {8, 9, 10, 11, 14, 15, 17, 18, 21, 24, 25, 43, 44, 45, 84}


class SteamworksError(RuntimeError):
    def __init__(self, message, *, result_code=None, outcome_unknown=False):
        super().__init__(message)
        self.result_code = result_code
        self.outcome_unknown = outcome_unknown


def parse_file_id(value):
    text = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,20}', text) or not 0 < int(text) <= _MAX_HANDLE:
        raise ValueError('Workshop ID 必须是有效的正 uint64 十进制整数')
    return int(text)


def _steam_library_roots(system):
    if system == 'Windows':
        roots = [Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam',
                 Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Steam']
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (0, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\Valve\Steam', 0, winreg.KEY_READ | view) as key:
                        for name in ('SteamPath', 'InstallPath'):
                            try:
                                value, _ = winreg.QueryValueEx(key, name)
                            except OSError:
                                continue
                            roots.insert(0, Path(value))
                except OSError:
                    continue
    elif system == 'Darwin':
        roots = [Path.home() / 'Library/Application Support/Steam']
    else:
        roots = [Path.home() / '.steam/steam', Path.home() / '.local/share/Steam']
    for root in tuple(roots):
        try:
            raw = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for match in re.finditer(r'"path"\s*"([^"]+)"', raw):
            library = Path(match.group(1).replace('\\\\', '\\'))
            if library.is_absolute() and library not in roots:
                roots.append(library)
    return list(dict.fromkeys(roots))


def find_dylib(override=None):
    selected = override or os.environ.get(DYLIB_ENV)
    if selected:
        path = Path(selected).expanduser().resolve()
        return path if path.is_file() else None
    system = platform.system()
    candidates = {
        'Windows': ('steam_api64.dll', 'RimWorldWin64/steam_api64.dll',
                    'RimWorldWin64_Data/Plugins/x86_64/steam_api64.dll'),
        'Darwin': ('RimWorld.app/Contents/MacOS/libsteam_api.dylib',
                   'RimWorldMac.app/Contents/PlugIns/steam_api.bundle/Contents/MacOS/libsteam_api.dylib'),
        'Linux': ('libsteam_api.so', 'RimWorldLinux_Data/Plugins/x86_64/libsteam_api.so'),
    }.get(system, ())
    roots = _steam_library_roots(system) if candidates else ()
    for location in candidates:
        for root in roots:
            path = root / 'steamapps/common/RimWorld' / location
            if path.is_file():
                return path.resolve()
    return None


def workshop_package_index(app_id=APPID):
    """Map installed Workshop content packageIds to (item_id, name) for dependency links."""
    index = {}
    for root in _steam_library_roots(platform.system()):
        content = root / 'steamapps' / 'workshop' / 'content' / str(app_id)
        try:
            items = sorted(content.iterdir())
        except OSError:
            continue
        for item in items:
            if not item.name.isdigit():
                continue
            try:
                metadata = ET.fromstring((item / 'About' / 'About.xml').read_bytes())
            except (OSError, ET.ParseError):
                continue
            # The first packageId is the item's own identity; later ones belong to its dependencies.
            package = next((node.text or '' for node in metadata.findall('packageId')), '').strip()
            if not package:
                continue
            name = (metadata.findtext('name') or '').strip()
            index.setdefault(package.casefold(), (int(item.name), name))
    return index


def sdk_profile():
    """Identify the supported ABI, not the presence of a compatible library/session."""
    system, arch = platform.system(), platform.machine().lower()
    arch = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(arch, arch)
    if (system not in ('Windows', 'Darwin', 'Linux') or C.sizeof(C.c_void_p) != 8
            or sys.byteorder != 'little' or (arch != 'x86_64' and (system, arch) != ('Darwin', 'arm64'))):
        raise SteamworksError(f'Steamworks 后端不支持此 Python 平台/架构：{system} {arch} {C.sizeof(C.c_void_p) * 8}-bit')
    # Valve steamclientpublic.h sets CALLBACK_PACK_SMALL for Linux/macOS.
    return {'system': system, 'architecture': arch, 'callbackPack': 8 if system == 'Windows' else 4}


def _packed(name, pack, fields):
    # The MS-style _pack_ option supplies the requested alignment on all hosts.
    return type(name, (C.Structure,), {'_layout_': 'ms', '_pack_': pack, '_fields_': fields})


def _abi(pack):
    u64, i32, u32 = C.c_uint64, C.c_int32, C.c_uint32
    return {
        'message': _packed('CallbackMsg', pack, [('user', i32), ('callback', i32),
                            ('data', C.c_void_p), ('size', i32)]),
        'completed': _packed('CallCompleted', pack, [('call', u64), ('callback', i32), ('size', u32)]),
        'create': _packed('CreateItemResult', pack, [('result', i32), ('file_id', u64), ('needs_accept', C.c_bool)]),
        'submit': _packed('SubmitItemUpdateResult', pack, [('result', i32), ('needs_accept', C.c_bool), ('file_id', u64)]),
        'query': _packed('QueryResultPrefix', pack, [('handle', u64), ('result', i32), ('returned', u32), ('total', u32)]),
        'details': _packed('UGCDetailsPrefix', pack, [('file_id', u64), ('result', i32), ('file_type', i32),
                           ('creator_app_id', u32), ('consumer_app_id', u32), ('title', C.c_char * 129),
                           ('description', C.c_char * 8000), ('owner', u64), ('created', u32), ('updated', u32),
                           ('added', u32), ('visibility', i32)]),
        # GetAppDependenciesResult_t arrives as 148 bytes whose field offsets differ by platform;
        # _app_dependencies() locates them by validating the item ID instead of trusting one layout.
        'appDependencies': _packed('AppDependenciesResult', 1, [('result', i32), ('payload', C.c_uint8 * 144)]),
    }


def _result_ok(result, label, *, mutation=False):
    if result != 1:
        raise SteamworksError(f'{label} 失败：{result}({_ERESULT.get(result, "UnknownEResult")})',
                              result_code=result, outcome_unknown=mutation and result not in _DEFINITE_REJECTIONS)


def _utf8(value):
    if '\x00' in value:
        raise ValueError('Steamworks 文本或路径不能包含 NUL')
    return value.encode('utf-8')


def _absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('Steamworks 文件参数必须是在打开 Steam 会话前确定的绝对路径')
    return _utf8(str(path))


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@contextmanager
def _quiet_native_output():
    """Keep native SDK diagnostics (including SteamID logs) out of CLI output."""
    with ExitStack() as cleanup:
        sink = cleanup.enter_context(open(os.devnull, 'wb', buffering=0))
        if os.name == 'nt':
            import msvcrt
            # The SDK has a statically linked CRT. Redirect the Win32 handles
            # before loading it; replacing only Python stdout does not work.
            kernel = C.WinDLL('kernel32', use_last_error=True)
            get, set_ = kernel.GetStdHandle, kernel.SetStdHandle
            get.restype, get.argtypes = C.c_void_p, [C.c_int32]
            set_.restype, set_.argtypes = C.c_int32, [C.c_int32, C.c_void_p]
            for number in (-11, -12):
                original = get(number)
                if not set_(number, msvcrt.get_osfhandle(sink.fileno())):
                    raise C.WinError(C.get_last_error())
                cleanup.callback(set_, number, original)
        else:
            sys.stdout.flush()
            sys.stderr.flush()
            fflush = C.CDLL(None).fflush
            fflush.restype, fflush.argtypes = C.c_int, [C.c_void_p]
            fflush(None)
            for number in (1, 2):
                original = os.dup(number)
                cleanup.callback(os.close, original)
                os.dup2(sink.fileno(), number)
                cleanup.callback(os.dup2, original, number)
            cleanup.callback(fflush, None)
        yield


class SteamworksUGC:
    def __init__(self, dylib, run_dir=DEFAULT_RUN_DIR, timeout=600):
        if not 0 < timeout <= 86400:
            raise ValueError('Steamworks timeout 必须大于 0 且不超过 86400 秒')
        self.dylib = Path(dylib).expanduser().resolve()
        self.run_dir = Path(run_dir).expanduser().resolve()
        self.timeout = timeout
        self.profile = sdk_profile()
        self._types = _abi(self.profile['callbackPack'])
        self._cleanup = None
        self._updates = {}

    def __enter__(self):
        if not _SESSION.acquire(blocking=False):
            raise SteamworksError('本进程已有一个 Steamworks 会话')
        with ExitStack() as cleanup:
            cleanup.callback(_SESSION.release)
            if not self.dylib.is_file():
                raise SteamworksError(f'Steamworks 库不存在：{self.dylib}')
            cleanup.enter_context(_quiet_native_output())
            self._lib = C.CDLL(str(self.dylib))
            self._bind()
            if not self._lib.SteamAPI_IsSteamRunning():
                raise SteamworksError('桌面 Steam 客户端未运行；请用户启动并登录')
            self.run_dir.mkdir(parents=True, exist_ok=True)
            work = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix='session-', dir=self.run_dir)))
            (work / 'steam_appid.txt').write_text(f'{APPID}\n', encoding='ascii')
            cleanup.callback(os.chdir, Path.cwd())
            os.chdir(work)
            cleanup.callback(_restore_env, {key: os.environ.get(key) for key in _APP_ENV})
            os.environ.update({key: str(APPID) for key in _APP_ENV})
            error_text = C.create_string_buffer(1024)
            status = self._lib.SteamAPI_InitFlat(error_text)
            if status != 0:
                raise SteamworksError(f'SteamAPI_InitFlat 失败 ({status})：{error_text.value.decode("utf-8", "replace")}')
            cleanup.callback(self._lib.SteamAPI_Shutdown)
            self._pipe = self._lib.SteamAPI_GetHSteamPipe()
            self._ugc = self._lib.SteamAPI_SteamUGC_v021()
            self._user = self._lib.SteamAPI_SteamUser_v023()
            utils = self._lib.SteamAPI_SteamUtils_v010()
            if not self._pipe or not self._ugc or not self._user or not utils:
                raise SteamworksError('Steam API 初始化后未获得必需的 pipe、UGC、User 或 Utils 接口')
            if self._lib.SteamAPI_ISteamUtils_GetAppID(utils) != APPID:
                raise SteamworksError('Steam API AppID 与 RimWorld (294100) 不符；已停止')
            self._lib.SteamAPI_ManualDispatch_Init()
            self._cleanup = cleanup.pop_all()
        return self

    def __exit__(self, *exc):
        try:
            if self._cleanup is not None:
                self._cleanup.close()
        finally:
            self._cleanup = None
            self._updates.clear()

    def _bind(self):
        void, u64, u32, i32, char, flag = C.c_void_p, C.c_uint64, C.c_uint32, C.c_int32, C.c_char_p, C.c_bool
        specs = {
            'SteamAPI_InitFlat': (i32, [void]),
            'SteamAPI_IsSteamRunning': (flag, []),
            'SteamAPI_Shutdown': (None, []),
            'SteamAPI_GetHSteamPipe': (i32, []),
            'SteamAPI_SteamUGC_v021': (void, []),
            'SteamAPI_SteamUser_v023': (void, []),
            'SteamAPI_SteamUtils_v010': (void, []),
            'SteamAPI_ISteamUser_BLoggedOn': (flag, [void]),
            'SteamAPI_ISteamUser_GetSteamID': (u64, [void]),
            'SteamAPI_ISteamUtils_GetAppID': (u32, [void]),
            'SteamAPI_ManualDispatch_Init': (None, []),
            'SteamAPI_ManualDispatch_RunFrame': (None, [i32]),
            'SteamAPI_ManualDispatch_GetNextCallback': (flag, [i32, C.POINTER(self._types['message'])]),
            'SteamAPI_ManualDispatch_FreeLastCallback': (None, [i32]),
            'SteamAPI_ManualDispatch_GetAPICallResult': (flag, [i32, u64, void, i32, i32, C.POINTER(flag)]),
        }
        ugc = {
            'CreateItem': (u64, [void, u32, i32]), 'StartItemUpdate': (u64, [void, u32, u64]),
            'SetItemVisibility': (flag, [void, u64, i32]), 'AddItemPreviewFile': (flag, [void, u64, char, i32]),
            'RemoveItemPreview': (flag, [void, u64, u32]), 'SubmitItemUpdate': (u64, [void, u64, char]),
            'CreateQueryUGCDetailsRequest': (u64, [void, C.POINTER(u64), u32]),
            'SetLanguage': (flag, [void, u64, char]), 'SetReturnLongDescription': (flag, [void, u64, flag]),
            'SetAllowCachedResponse': (flag, [void, u64, u32]), 'SetReturnAdditionalPreviews': (flag, [void, u64, flag]),
            'SendQueryUGCRequest': (u64, [void, u64]), 'GetQueryUGCResult': (flag, [void, u64, u32, void]),
            'GetQueryUGCPreviewURL': (flag, [void, u64, u32, void, u32]),
            'GetQueryUGCNumAdditionalPreviews': (u32, [void, u64, u32]),
            'GetQueryUGCAdditionalPreview': (flag, [void, u64, u32, u32, void, u32, void, u32, C.POINTER(i32)]),
            'ReleaseQueryUGCRequest': (flag, [void, u64]),
        }
        ugc.update({name: (flag, [void, u64, char]) for name in ('SetItemTitle', 'SetItemDescription',
                   'SetItemPreview', 'SetItemContent', 'SetItemUpdateLanguage')})
        specs.update({'SteamAPI_ISteamUGC_' + name: spec for name, spec in ugc.items()})
        missing = [name for name in specs if not hasattr(self._lib, name)]
        if missing:
            raise SteamworksError('Steamworks 库接口不兼容（需 InitFlat、UGC v021、User v023 及手动回调导出）：'
                                  + ', '.join(missing))
        for name, (result, params) in specs.items():
            fn = getattr(self._lib, name)
            fn.restype, fn.argtypes = result, params

    def _bind_dependencies(self):
        """Bind the Required Items/DLC calls on first use, so uploads never depend on them."""
        if hasattr(self, '_dependency_specs'):
            return
        void, u64, u32, i32, flag = C.c_void_p, C.c_uint64, C.c_uint32, C.c_int32, C.c_bool
        specs = {
            'SteamAPI_ISteamUGC_AddDependency': (flag, [void, u64, u64]),
            'SteamAPI_ISteamUGC_AddAppDependency': (flag, [void, u64, u32]),
            'SteamAPI_ISteamUGC_SetReturnChildren': (flag, [void, u64, flag]),
            'SteamAPI_ISteamUGC_GetQueryUGCChildren': (i32, [void, u64, u32, C.POINTER(u64), u32]),
            'SteamAPI_ISteamUGC_GetAppDependencies': (u64, [void, u64]),
        }
        missing = [name for name in specs if not hasattr(self._lib, name)]
        if missing:
            raise SteamworksError('Steamworks 库缺少必需项目/DLC 依赖接口：' + ', '.join(missing))
        for name, (result, params) in specs.items():
            fn = getattr(self._lib, name)
            fn.restype, fn.argtypes = result, params
        self._dependency_specs = specs

    def logged_on(self):
        return bool(self._lib.SteamAPI_ISteamUser_BLoggedOn(self._user))

    def steam_id(self):
        return self._lib.SteamAPI_ISteamUser_GetSteamID(self._user)

    def _wait_apicall(self, call, expected, layout, label, *, timeout=None, mutation=False):
        if not call:
            raise SteamworksError(f'{label} 未返回有效 API 调用句柄', outcome_unknown=mutation)
        budget = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + budget
        message = self._types['message']()
        completed = self._types['completed']
        lib = self._lib
        while time.monotonic() < deadline:
            lib.SteamAPI_ManualDispatch_RunFrame(self._pipe)
            while time.monotonic() < deadline and lib.SteamAPI_ManualDispatch_GetNextCallback(self._pipe, C.byref(message)):
                try:
                    if message.callback == 704:
                        raise SteamworksError(f'{label}：Steam 客户端正在关闭', outcome_unknown=mutation)
                    if message.callback != 703:  # SteamAPICallCompleted_t
                        continue
                    if not message.data or message.size < C.sizeof(completed):
                        raise SteamworksError(f'{label}：完成回调头无效', outcome_unknown=mutation)
                    ready = completed.from_buffer_copy(C.string_at(message.data, C.sizeof(completed)))
                    if ready.call != call:
                        continue
                    if ready.callback != expected or not C.sizeof(layout) <= ready.size <= 65536:
                        raise SteamworksError(f'{label}：回调 ID 或长度与 SDK ABI 不符：{ready.callback}/{ready.size}',
                                              outcome_unknown=mutation)
                    raw, failed = C.create_string_buffer(ready.size), C.c_bool()
                    available = lib.SteamAPI_ManualDispatch_GetAPICallResult(
                        self._pipe, call, raw, ready.size, expected, C.byref(failed))
                    if failed.value or not available:
                        raise SteamworksError(f'{label}：无法取得成功的 Steam 回调（I/O 或结果读取失败）',
                                              outcome_unknown=mutation)
                    return layout.from_buffer_copy(raw)
                finally:
                    lib.SteamAPI_ManualDispatch_FreeLastCallback(self._pipe)
            time.sleep(.05)
        raise SteamworksError(f'{label}：等待 Steam 回调超时（{budget}s）', outcome_unknown=mutation)

    def _ugc_call(self, name, *args):
        return getattr(self._lib, 'SteamAPI_ISteamUGC_' + name)(self._ugc, *args)

    def _setter(self, name, *args):
        if not self._ugc_call(name, *args):
            raise SteamworksError(f'{name} 被 Steam API 拒绝')

    def create_item(self):
        call = self._ugc_call('CreateItem', APPID, 0)
        result = self._wait_apicall(call, 3403, self._types['create'], 'CreateItem', mutation=True)
        _result_ok(result.result, 'CreateItem', mutation=True)
        if not result.file_id:
            raise SteamworksError('CreateItem 成功回调没有物品 ID', outcome_unknown=True)
        return result.file_id, bool(result.needs_accept)

    def start_update(self, file_id):
        file_id = parse_file_id(file_id)
        handle = self._ugc_call('StartItemUpdate', APPID, file_id)
        if handle in (0, _MAX_HANDLE):
            raise SteamworksError('StartItemUpdate 返回无效句柄')
        self._updates[handle] = file_id
        return handle

    def set_title(self, handle, text):
        self._setter('SetItemTitle', handle, _utf8(text))

    def set_description(self, handle, text):
        self._setter('SetItemDescription', handle, _utf8(text))

    def set_preview(self, handle, path):
        self._setter('SetItemPreview', handle, _absolute(path))

    def set_content(self, handle, path):
        self._setter('SetItemContent', handle, _absolute(path))

    def set_visibility(self, handle, value):
        self._setter('SetItemVisibility', handle, value)

    def set_update_language(self, handle, language):
        self._setter('SetItemUpdateLanguage', handle, _utf8(language))

    def add_screenshot(self, handle, path):
        self._setter('AddItemPreviewFile', handle, _absolute(path), 0)

    def remove_screenshot(self, handle, index):
        self._setter('RemoveItemPreview', handle, index)

    def add_dependency(self, handle, child):
        """Queue a Workshop Required Items entry for the next submit."""
        self._bind_dependencies()
        self._setter('AddDependency', handle, parse_file_id(child))

    def add_app_dependency(self, handle, app_id):
        """Queue a DLC the player must own for the next submit."""
        self._bind_dependencies()
        self._setter('AddAppDependency', handle, app_id)

    def query_dependencies(self, file_id):
        """Read the Required Items and DLC dependencies Steam currently holds for one item."""
        self._bind_dependencies()
        file_id = parse_file_id(file_id)
        return {'items': self._children(file_id), 'apps': self._app_dependencies(file_id)}

    def _children(self, file_id):
        ids = (C.c_uint64 * 1)(file_id)
        q = self._ugc_call('CreateQueryUGCDetailsRequest', ids, 1)
        if q in (0, _MAX_HANDLE):
            raise SteamworksError('CreateQueryUGCDetailsRequest 返回无效句柄')
        try:
            for option, value in (('SetReturnChildren', True), ('SetAllowCachedResponse', 0)):
                self._setter(option, q, value)
            call = self._ugc_call('SendQueryUGCRequest', q)
            reply = self._wait_apicall(call, 3401, self._types['query'], 'SendQueryUGCRequest')
            _result_ok(reply.result, 'SendQueryUGCRequest')
            if reply.handle != q or reply.returned != 1:
                raise SteamworksError('必需项目查询未返回请求的唯一结果（可能不存在或当前账户不可见）')
            children = (C.c_uint64 * 64)()
            # Older libraries return a count and newer ones a flag; the zeroed buffer serves both.
            self._ugc_call('GetQueryUGCChildren', q, 0, children, 64)
            return [value for value in children if value]
        finally:
            self._ugc_call('ReleaseQueryUGCRequest', q)

    def _app_dependencies(self, file_id):
        call = self._ugc_call('GetAppDependencies', file_id)
        reply = self._wait_apicall(call, 3416, self._types['appDependencies'], 'GetAppDependencies')
        _result_ok(reply.result, 'GetAppDependencies')
        raw = bytes(reply.payload)  # message bytes 4..148; the count is the last word of both layouts
        count = struct.unpack_from('<I', raw, 140)[0]
        # (item ID, AppId[32]) start at message offset 4 on pack-4 platforms (observed on macOS)
        # and at 8 with the 64-bit alignment of pack-8 Windows.
        for offset in (0, 4):
            item, *apps = struct.unpack_from('<Q32I', raw, offset)
            if item == file_id and count <= 32:
                return apps[:count]
        raise SteamworksError('DLC 依赖回读的数据布局与已知布局不符，无法确认结果')

    def submit(self, handle, changenote=''):
        file_id = self._updates.pop(handle, None)
        if file_id is None:
            raise SteamworksError('SubmitItemUpdate 没有对应的有效且未提交的目标')
        call = self._ugc_call('SubmitItemUpdate', handle, _utf8(changenote or ''))
        result = self._wait_apicall(call, 3404, self._types['submit'], 'SubmitItemUpdate', mutation=True)
        _result_ok(result.result, 'SubmitItemUpdate', mutation=True)
        if result.file_id != file_id:
            raise SteamworksError('SubmitItemUpdate 回调的物品 ID 与请求目标不符', outcome_unknown=True)
        return {'result': result.result, 'needsAccept': bool(result.needs_accept), 'fileId': result.file_id}

    def query_details(self, file_id, language='english'):
        file_id = parse_file_id(file_id)
        ids = (C.c_uint64 * 1)(file_id)
        q = self._ugc_call('CreateQueryUGCDetailsRequest', ids, 1)
        if q in (0, _MAX_HANDLE):
            raise SteamworksError('CreateQueryUGCDetailsRequest 返回无效句柄')
        try:
            for option, value in (('SetLanguage', _utf8(language)), ('SetReturnLongDescription', True),
                                  ('SetReturnAdditionalPreviews', True), ('SetAllowCachedResponse', 0)):
                self._setter(option, q, value)
            call = self._ugc_call('SendQueryUGCRequest', q)
            reply = self._wait_apicall(call, 3401, self._types['query'], 'SendQueryUGCRequest')
            _result_ok(reply.result, 'SendQueryUGCRequest')
            if reply.handle != q or reply.returned != 1:
                raise SteamworksError('工坊查询未返回请求的唯一结果（可能不存在或当前账户不可见）')
            # Native SDK fills the full current struct; parse only the stable prefix we use.
            raw = C.create_string_buffer(65536)
            if not self._ugc_call('GetQueryUGCResult', q, 0, raw):
                raise SteamworksError('GetQueryUGCResult 失败')
            details = self._types['details'].from_buffer_copy(raw)
            _result_ok(details.result, 'GetQueryUGCResult')
            if details.file_id != file_id:
                raise SteamworksError('工坊查询结果的物品 ID 与请求不符')
            root_preview = C.create_string_buffer(4096)
            self._ugc_call('GetQueryUGCPreviewURL', q, 0, root_preview, len(root_preview))
            count = self._ugc_call('GetQueryUGCNumAdditionalPreviews', q, 0)
            if count > 4096:
                raise SteamworksError('工坊查询返回了异常的附加预览数')
            previews = []
            for index in range(count):
                url, filename, kind = C.create_string_buffer(4096), C.create_string_buffer(1024), C.c_int32()
                if not self._ugc_call('GetQueryUGCAdditionalPreview', q, 0, index, url, len(url), filename, len(filename), C.byref(kind)):
                    raise SteamworksError(f'工坊附加预览 {index} 未能读取')
                previews.append({'index': index, 'type': kind.value, 'url': url.value.decode('utf-8', 'replace'),
                                 'originalFileName': filename.value.decode('utf-8', 'replace')})
            return {'publishedFileId': file_id, 'fileId': file_id, 'language': language, 'creatorAppId': details.creator_app_id,
                    'consumerAppId': details.consumer_app_id, 'ownerSteamId': details.owner,
                    'title': details.title.decode('utf-8', 'replace'), 'description': details.description.decode('utf-8', 'replace'),
                    'visibility': details.visibility, 'previewUrl': root_preview.value.decode('utf-8', 'replace'),
                    'screenshotCount': count, 'additionalPreviewCount': count, 'screenshots': previews}
        finally:
            self._ugc_call('ReleaseQueryUGCRequest', q)
