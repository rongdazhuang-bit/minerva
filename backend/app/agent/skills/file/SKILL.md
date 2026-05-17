# file

工作区**沙箱**内的文件与目录操作（非用户本机磁盘）。路径均为相对沙箱根目录，禁止 `..` 与绝对路径。

## 何时使用

**Planner 必选本 skill（`skill_id=file`）**：用户要查看、列出、读取、写入、删除、创建或移动**沙箱/工作区**内的文件或目录时，必须选 file。禁止使用 `general`（general 无文件工具，会错误建议用户自己在本机执行 `ls`/`dir`）。

**子 Agent 执行**：进入本 skill 后根据目标调用 `list_dir`、`read_file`、`write_file` 等工具；「当前目录/根目录」在沙箱中指 `path=""`。根据工具返回 JSON 向用户说明结果。

## Planner 路由

- 列出当前目录
- 列出目录
- 列出文件
- 当前目录文件
- 目录下有什么
- 有哪些文件
- 读取文件
- 读取沙箱
- 读取
- 写入
- 删除
- 查看文件内容
- 写入文件
- 创建文件
- 保存文件
- 删除文件
- 删除目录
- 创建目录
- 新建文件夹
- 移动文件
- 重命名文件
- 沙箱目录
- 沙箱文件
- 工作区文件
- 工作区目录
- 列出根目录
- list_dir
- list directory

## 工具一览

| 工具 | 说明 |
|------|------|
| `list_dir` | 列出目录直接子项（`path` 默认 `""` 为沙箱根） |
| `read_file` | 读取 UTF-8 文本（超限返回 `too_large`） |
| `write_file` | 创建或覆盖写入（`create_parents` 默认 true） |
| `delete_path` | 删除文件或目录（非空目录需 `recursive=true`） |
| `mkdir` | 创建目录（`parents` 默认 true） |
| `move_path` | 移动或重命名（`src` → `dest`） |

## 返回格式

所有工具返回 JSON 字符串：成功含 `"ok": true`；失败含 `"ok": false`, `"error"`, `"code"`。
