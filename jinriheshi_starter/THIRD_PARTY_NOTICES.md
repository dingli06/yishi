# 第三方内容与来源记录

## HowToCook 菜谱正文

- 原项目：<https://github.com/Anduin2017/HowToCook>
- 本数据包固定版本：`0e106eea348c734fe1586f781202994439cf98a5`
- 上游许可证：`Unlicense`。本包原样保留于
  `data/raw/howtocook/0e106eea348c734fe1586f781202994439cf98a5/LICENSE`。
- 上游 README 同目录原样保留；不会将其中的部署方法或默认凭据作为本项目设置。
- 收录范围：`dishes/` 下 372 个非模板 Markdown 文件，加上原 LICENSE 与 README，共 374 个文件。
- 来源目录中含饮料、调料、半成品等，372 是文档数，不代表 372 个完整正餐或去重后的菜品数。
- 每个原始文件都以 Git blob SHA-1 校验，并另存 SHA-256、字节数、固定版本 URL，见 `data/sources/howtocook.lock.json`。
- 原始文本保留用于追溯；派生记录需要保留来源和原文证据。上游的宣传性健康描述不应自动成为本产品推荐标签。

## 图片、视频与外部链接

本包没有下载或分发上游图片、视频文件。原 Markdown 可能包含图片路径及外链，这些属于原文记录，不表示相关媒体已经获得独立审核或可用于本产品展示。前端应按本项目媒体发布状态决定是否展示；不能直接加载所有原文外链。

## 本项目代码与文档

HowToCook 的 Unlicense 仅标识引用的上游内容。本交付不替项目所有者决定新增代码、标注与文档的对外开源许可证。

## 完整性复核

```bash
python scripts/fetch_howtocook.py --verify-only
```

该命令不联网、不更新版本、不修改文件；发现漏文件、文件内容变化、清单字段不一致或目录逃逸时失败。后续更新必须显式传入新的完整 Git SHA，例如 `--revision <40位SHA>`，不能默认追踪 `master`。
