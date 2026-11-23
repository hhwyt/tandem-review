[English](README.md) | **简体中文**

# Tandem Review

<p align="center"><img src="brand/tandem.svg" alt="Tandem：人和 agent 骑着双人自行车，路面是一行行代码" width="560"></p>

**人掌方向，agent 出力，一起 review。**

Tandem Review 是一个浏览器页面，让人和编程 agent 一起 review 一份改动：agent 准备好讲解，
人来阅读、判断、写评论，agent 按评论修改，然后进入下一轮。

只要 agent 能写 JSON 文件、能跑命令行，就能接入：Claude Code、Codex、DeepSeek 等都可以。

## review 的人会看到什么

1. **先看总览。** 改动的总结、需要拍板的决定、背景、做法、一张「改动挂在哪」的图、覆盖了什么
   没覆盖什么，以及每个文件一句话的作用。
2. **按理解顺序读。** 函数按代码实际执行的路径分成章节，先读调用方再读被调用方，每个函数都在
   上下文里读。关键函数标 ⚑。另有按文件查看的模式。
3. **行间说明。** agent 对每段代码的讲解以淡色的一行显示在对应代码上方，复制代码时不会带上，
   一个键就能隐藏。
4. **调用关系。** 侧栏用树展示当前函数被谁调用、从哪些入口进来、它又调用了谁。改动里的函数在
   页面内跳转，其他函数在编辑器里打开。
5. **评论一次发出。** 对一行或一段写评论，分「必须改 / 后续 / 提问」，一次发给 agent。agent
   回复改了什么，进入下一轮。

界面支持英文和中文，在右上角切换。

## 进度

设计阶段。[`prototypes/`](prototypes/) 里是可点击的原型，用一个真实的 TiDB PR 做示例数据。
用本地静态服务打开 `prototypes/app.html` 即可。

v1 计划：

- `review.json`：agent 写出的数据格式（总览、章节、函数、说明、调用关系，中英两版）。
- 只用 Python 标准库的本地服务：只监听 127.0.0.1，每次会话一个 token；提供页面，评论边写边存。
- `tandem wait`：等 review 的人发送评论，把评论以 Markdown 打给 agent，同时写一份
  `comments-round-N.md`。
- 一个 agent skill：说明怎么准备 review、打开页面、按评论修改、进入下一轮。

## 协议

[MIT](LICENSE)
