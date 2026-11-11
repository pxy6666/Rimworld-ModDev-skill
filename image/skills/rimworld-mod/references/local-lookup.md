# 批量查证：当前安装与上游

先锁定目标及游戏根。用本机 Version.txt、实际 Assembly-CSharp.dll 哈希和明确上游来源绑定证据；缓存目录名、时间或相同大版本都不能代替身份。重复任务复用同一缓存目录。脚本随 Basic/Image 分发，工程 tools/mod.ps1 lookup / decomp 是可选包装入口。

```text
python <技能>/scripts/lookup.py def --game-root <游戏根> --target 1.7 ThingDef:EndTable ThingDef:Bed
python <技能>/scripts/lookup.py type --game-root <游戏根> --target 1.7 --cache-dir <工具工作区>/.local/lookup Thing Plant Skyfaller CompProperties_Facility
python <技能>/scripts/lookup.py member --game-root <游戏根> --target 1.7 --cache-dir <同一索引目录> 'Verse.ThingDef::comps' 'RimWorld.WorkGiver_DoBill::*'
python <技能>/scripts/lookup.py refs --game-root <游戏根> --target 1.7 --cache-dir <同一索引目录> 'Verse.ThingDef::comps'
```

- def 一批取回多个节点、父链候选及源文件哈希；本地 XML 索引只重读新增/变化文件。不写索引用 --no-cache；如还需禁用 Python 字节码写入，用 python -B。可重复传 --def-root 指明已确认的上游内容根/Defs。数据不是启用列表，不合并继承或执行补丁。输出截断时按文件局部读。
- type/member/refs 首次用已有 .NET SDK 建元数据索引，不执行游戏 DLL；同构建/同 DLL 指纹时复用。短名有多个候选时选全名，补丁目标核对重载。显式追加 --dll 可查上游。静态引用不等于运行调用，反射、动态注册和已应用补丁需另查。
- 不为查 XML 安装 SDK 或 ILSpy；只读原文件也能继续。catalog.py 的画像、验证、精选条目及样例留作已记录构建的辅助资料；旧构建不是当前签名证明。

## 需要方法体时才准备源码缓存

先查同构建清单。没有缓存且有多项源码调查时，用现有 ilspycmd 一次生成，同时查 XML/整理需求；单项可定点取证。生成写工具工作区 .local，旧缓存不覆盖，未完成/无指纹的目录不当证据，产物不进入分发或 mod。

```text
python <技能>/scripts/source_cache.py inspect --game-root <游戏根> --target 1.7 --cache-dir <工具工作区>/.local/source-cache
python <技能>/scripts/source_cache.py build --game-root <游戏根> --target 1.7 --cache-dir <同一目录> --ilspy <已有可执行文件>
python <技能>/scripts/source_cache.py locate --game-root <游戏根> --target 1.7 --cache-dir <同一目录> --type <完整类型名> --member <成员>
```

查上游源码加 --dll <实际引用 DLL>；定位返回候选路径，按成员名局部读取，不将反编译源码复制进 mod。缺能力转 setup，只准备必要组件。工程 doctor 把旧画像/过期缓存作为证据警告，并检查工程默认缓存；共享路径用 decomp inspect 指定同一 --cache-dir。

## 已有工具在哪里找

优先用本技能相邻脚本，或当前目标工程的已知工具；再用明确识别、可访问的父工具工作区。确认脚本路径、参数及数据版本，用绝对脚本路径与显式目标根调用。复用工具不等于沿用父工程的身份、编译参数或覆盖路径；不盲执行未知祖先的同名文件。

需要运行时合并 Def 时选覆盖当前组合的查询。若已知工作区有 tools/rimsage_query.ps1，可用 -Method List 看 schema，再做一次有关的 -Method Call 小查询并核对来源构建；列表成功只证明连通。来源未知或版本不符时仅作线索，不反复等待远程查询或自动改客户端配置。
