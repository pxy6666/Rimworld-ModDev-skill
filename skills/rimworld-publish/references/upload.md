# 上传与恢复

## 离线准备

`--content` 指发行包内 **`About/About.xml` 位于根下的那一个 Mod 目录**。用同一发行目录中与它同级的 `release-receipt.json` 和 `manifest.json` 核对目录和每个文件的 SHA-256。不要移动或手改 staging 来绕过校验；内容变化时重新打包和计划。

包收据只证明打包时的静态检查。另核对这份内容哈希在用户约定范围内的加载、玩法等验收证据；未完成的项目必须已获用户明确接受才作为例外纳入发布。`--acceptance <说明>` 必填，记录验收范围、证据引用或接受的例外，随该包哈希保存。验收通过或接受例外不等于授权上传。

在当前启用技能目录定位 `scripts/publish.py`，按 `--help` 核对所用版本的命令。Windows PowerShell 示例：

```powershell
# 新建：标题、主图、描述明确选定，未指定可见性时采用私密。
python -X utf8 <技能目录>/scripts/publish.py plan --content <已核验Mod目录> --create --project <工程根> --title <标题> --preview <主图路径> --description-file <描述正文> --journal <新本地记录.json> --acceptance '<验收范围与证据或已接受例外>'
# 现有物品；已有受核验的 About/PublishedFileId.txt 时可由计划解析目标。
python -X utf8 <技能目录>/scripts/publish.py plan --content <已核验Mod目录> --item-id <已确认ID> --description-file <描述正文> --changelog '<本次变更说明>' --journal <本地记录.json> --acceptance '<验收范围与证据或已接受例外>'
# 只读：读回物品现有页面与必需项目，不写 journal。
python -X utf8 <技能目录>/scripts/publish.py inspect --item-id <物品ID> --language english --language schinese
```

不确定目标时先核对现有物品 ID 与包标记；不能把 ID 缺失、失效或无权限当作创建授权。`--project <工程根>` 另核对项目身份。`plan` 即离线预览，保存包身份、内容校验、明确物品和写入范围，不连接 Steam，也不上传。journal 放在本地、上传内容根之外。

## 必做清单

每次发布提交下表全部项目，没有可选项；用户没有提到某一项不代表可以省略，`plan` 对缺项直接报错。“保留”指沿用 Steam 上已有的内容。

| 项目 | 要求 |
| --- | --- |
| Mod 内容 | 总是提交已核验的 Mod 内容 |
| 标题 | 新建必填；更新未指定则保留 |
| 描述 | 每次发布都提供正文（`--description-file`）。工程里没有页面文案源文件时先写一份：取自游戏内实际名称与说明、核实过的数值和 About.xml。已有物品而工程里没有源文件的，先用 `inspect` 读回现有页面存为源文件再改，不凭空覆盖 |
| 前置段 | 工具按 About.xml 生成并追加到每个写入的语言槽末尾，正文里不要手写。`modDependenciesByVersion`/`modDependencies`（各支持版本取并集）列为“必需”，带 DLC 标注和工坊链接；`loadAfterByVersion`/`loadAfter` 列为“加载顺序（非必需）”。依赖变了，页面随本次发布更新 |
| 必需项目与 DLC | 必需模组写入工坊的 Required Items（depends on），DLC 写为 DLC 依赖，再读回核对；不一致按 [执行和结果](#执行和结果) 处理 |
| 主图 | 新建必填；更新未指定则保留 |
| 其他语言槽 | 发行包 `Languages/` 带哪些语言，就用 `--locale LANGUAGE=FILE` 为哪些语言各提供标题和描述；每槽两项都要有，Steam 按语言分别保存。未声明的语言保留 |
| 变更说明 | 更新必填（`--changelog`），取自工程变更记录；不代替页面描述 |
| 截图 | 每次都向用户要，见“由用户决定” |
| PublishedFileId.txt | 新建后必做，见“首次发布” |

`--language` 指定正文文件对应语言槽，省略时用 Steam 默认槽。正文是 UTF-8 文本，其他语言槽是只含 `title` 和 `description` 的 UTF-8 JSON。依赖声明里缺工坊链接的模组，按本机已安装的工坊内容反查 packageId；仍解析不了的必需模组只显示名称和 packageId，状态里列为 `unresolved`：请用户在 About.xml 补 `steamWorkshopUrl` 后重新计划，或在网页手动添加。

## 由用户决定

只有两项由用户决定。

- **可见性**：`--visibility public|friends-only|private|unlisted`。现有物品不指定则保持原状，新物品默认私密。转公开是独立选择，单独确认。
- **截图**：只有用户能提供。计划前向用户要本次要展示的截图（最多 20 张）；用户没有或明确本次不带、保留现有图库时，在计划里写明这个结论，不自行决定。`--replace-screenshots <图片路径 ...>` 明确替换图库；只写标记、不带路径表示清空；不带该参数不触碰图库。

主图或截图超过 1MB 时自动压缩**同一张图**（不替换内容）：主图重编码为 PNG、必要时逐步缩小但保持 512×512 以上（PNG 仍超限时最后尝试 256 色量化），截图重编码为 JPEG 并逐级降低质量；压缩副本保存在 journal 同级的 `<journal 名>.assets/` 目录并计入哈希校验。自动压缩需要 Pillow（`python -m pip install pillow`），未安装时明确报错，由用户提供小于 1MB 的图。

Steam 提示须接受工坊协议时，请用户在 Steam 处理并核对可见性。替换图库期间请停止在其它客户端编辑同一物品的预览。Steam 按位置移除预览；工具会在提交前重新核对图库，有变化就停止。

## 首次发布

新建分两轮，两轮都完成才算发布完成：

1. `plan --create` 后上传：创建物品（默认私密），提交内容与完整页面。这一轮的包里还没有物品标记。
2. `bind --journal <记录.json>` 把物品 ID 写回 `--project` 指定工程的 `About/PublishedFileId.txt`，与游戏自带上传器的做法一致。工程已绑定其他物品时工具拒绝覆盖，先向用户确认。
3. 回发行准备重新打包，让 `About/PublishedFileId.txt` 进入清单，再按“现有物品”计划并上传一次。两轮各用一份 journal，第一份在 `bind` 后才显示完成。

## 执行和结果

上传前核对用户已授权的目标、包哈希、页面变更以及当前 Steam 会话；按 [SDK 环境](sdk-env.md) 执行：

```powershell
python -X utf8 <技能目录>/scripts/publish.py upload --journal <本地记录.json>
python -X utf8 <技能目录>/scripts/publish.py status --journal <本地记录.json>
```

保留同一个 journal。每步各自报告状态，不把部分完成说成整次成功：`incomplete` 为空、`complete` 为 `true` 才算完成。

| 状态 | 下一步 |
| --- | --- |
| 已知失败 | 查明并纠正原因；目标和授权范围未变时，以原 journal 执行 `upload` 续未完成步骤。若改变了输入，重计划并保留旧记录 |
| 必需项目读回不一致（`failed`） | Steam 接受依赖写入并回报提交成功，但服务端可能不保留（2026-11-24 在 macOS 上实测被拒，新建的私密物品同样：必需模组 `File Not Found`、DLC `Access Denied`，原因未明），所以这一步只以读回为准。把 journal 里缺的物品和 DLC 列给用户，让其在工坊网页的 Required Items 手动添加；同一份计划不要反复重试，之后可用 `inspect` 复核 |
| 已完成 | 用返回的实际 ID 交付工坊链接和各必做项状态；必要时核对实际页面。上传完成不证明游戏内可用 |
| 结果未知（包括提交后连接断开、等待回执超时、提交回报 `2(Fail)`） | 停止自动重试，不另开 journal 规避。从 Steam 客户端、该物品的实际状态或可信回执核实该步结果。按物品 ID 和时间核查客户端日志：Windows 在 Steam 安装目录的 `logs/workshop_log.txt`，macOS 在 `~/Library/Application Support/Steam/logs/workshop_log.txt`。`Upload workshop item … failed (…)` 表示上传开始前就失败（2026-11-24 实测：更新已有物品时取旧清单遇到 CDN HTTP 502），读回确认未生效后 `resolve --outcome failed` 再续传；只有日志明确确认在提交生效前失败才可标为失败 |

只有掌握可信证据后才按实际结果 `resolve --journal <记录.json> --outcome completed|failed --evidence <证据说明>`；已知创建成功还要传 `--item-id <已核实的新ID>`。`failed` 只在确认该步未生效时使用。没有结论就保留未知并交代如何进一步核实。
