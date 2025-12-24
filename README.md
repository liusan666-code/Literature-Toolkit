# Literature-Toolkit

A small tool for organizing literature. It was mostly written by AI.

## 项目简介
- 基本由AI写的文献工具箱，用于重命名，抓取SI，清洗后上传notebooklm
- 请先在设置/config中填入希望使用的chrome data（建议复制一个默认的到新的文件夹），api key，左下角和日志的图片插入（可选）
- 记得使用校园网
- 目前只稳定接入deepseek api进行文献重命名、llm清洗和关键词抓取
- gemini api目前只用来llm清洗
- 提示词部分可以让程序外AI帮你写
- 在抓取SI阶段会存在命名过长截断现象，人机验证时需要手动点击

## 已知问题
- 自定义流程有多个小bug
- 列表顺序与程序顺序不符
- 存在历史记录后查看按钮不存在
