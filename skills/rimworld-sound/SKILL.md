---
name: rimworld-sound
description: Use when RimWorld 1.6/1.7 tasks need custom sound effects, audio editing, loops, animation sync, material-specific impacts, loudness control, or SoundDef playback validation.
---

# RimWorld 声音制作

先从真实消费者、播放事件和目标听感建立声音契约。技能负责声音设计、制作/编辑、试听与文件证据；`rimworld-mod` 负责 SoundDef、C# 触发、循环源和生命周期绑定，`rimworld-debug` 负责已绑定后的播放故障。

## 路由

| 任务 | 必读 |
| --- | --- |
| 描述、材质、尺度、距离、事件时序不清 | [声音 brief](references/sound-brief.md) |
| 从零制作、复用、剪辑、分层或外部生成 | [制作与来源](references/sound-production.md) |
| 起飞/降落、动画同步、巡航、持续音或无缝循环 | [循环与同步](references/looping-and-sync.md) |
| WAV/OGG、声道、采样率、峰值、响度或变速控制 | [响度与格式](references/loudness-and-format.md) |
| 导入、SoundDef 交接、试听与游戏验收 | [声音验收](references/sound-acceptance.md) |

## 工作合同

1. 先记录谁播放、什么事件、位置/距离、持续时间、材质与尺度、单次/循环、目标情绪和禁止混淆的材质。
2. 先交一张可试听样稿；用户要求变化时修改受影响层，不把整个声音重新合成。
3. 只用实际可用且获授权的音频工具或用户素材。工具不可用、来源未授权时停在 brief/提示词/缺口，不把 MIDI、波形说明或脚本执行结果冒充成音频。
4. 分层制作瞬态、主体、尾音和纹理；分别检查真实峰值、响度、低频堆积、开头/结尾瞬态及连续播放疲劳。
5. 循环时确认首尾波形和相位可拼接；动画同步按实际 tick/秒和事件状态执行。不要靠改变 pitch 或播放速率伪造任意飞行距离。
6. 保存来源、授权、工具/模型、最终文件、哈希、采样格式、时长、响度/峰值和试听证据。
7. 将最终文件、clip path、SoundDef 需求、播放位置、循环/一次性语义交给 `rimworld-mod` 绑定；本技能不自行改 C# 或 SoundDef。
8. 绑定后出现音量、循环断裂、暂停/读档失效、脱图、重复播放或触发错误时交给 `rimworld-debug`。

## 停止条件

缺少目标听感、来源授权、真实文件、可用试听/处理能力、可查询的消费者或动画事件时，准确停在对应阶段。文件能解码、XML 引用存在或本地播放一次都不等于游戏音效完成。
