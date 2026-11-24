# 建议：把"内容不完整"从 502 改为业务降级

> 提出方：VideoMind Bridge｜日期：2026-11-23
> 对象：`内容运营agent/api-server/services/VideoMindClient.js`
> 性质：**建议**，不影响当前运行；但我们这边修一个契约问题时发现了它，值得一起处理。

---

## 现象

`VideoMindClient.js` 第 154 行起：

```js
if (data.success !== true) {
  error.statusCode = data.error_code === 'unsupported_url' ? 422 : 502;
  error.errorCode = data.error_code;
  throw error;
}
```

即：只要上游判定"没成功"，一律映射成 **502 Bad Gateway**。

## 为什么这是个问题

**① 502 的语义不对。** RFC 9110 §15.6.3 定义 502 是"作为网关或代理，从上游收到了**无效响应**"。
"这个视频只抓到了标题"、"链接分享参数过期"、"笔记被设为私密"都不是无效响应，
它们是**有效的**业务结论。

**② 它把"部分可用"和"彻底失败"压成同一档。** 上游已经用 `completeness` 表达了完整度
（`full` / `meta` / `none`），下游也有自己的密度校验。再叠加一个 502，等于把
"可以降级使用的内容"和"什么都拿不到"混在一个错误通道里——你们自己的注释里
也写了 `completeness=full` 不可信、需要降级为 `partial`，说明这条区分是需要的。

**③ 它会掩盖真实的网关故障。** 真 502（本机服务没起、上游不可达）和"内容不完整"
混在一起，监控上无法区分。

## 建议的映射

| 上游情况 | 现状 | 建议 |
|---|---|---|
| 传输失败 / 超时 / 本机服务不可达 | 502 | **保持 502 / 503**（这才是网关类错误） |
| `success=false` + `error_code` 属"内容不可得"（`*_no_detail`、`xhs_note_unavailable`、`*_no_content`） | 502 | **422 或 200+partial 的业务降级** |
| `success=false` + `error_code` 属"需要动作"（`xhs_token_invalid`、`*_login_required`） | 502 | 422 + 提示用户重新分享/登录 |
| `success=true` + `completeness=meta` | 正常处理 | 走现有 `partial` 降级路径 |

## 上游配合

我们这边已把契约写进 [`docs/CONTRACT.md`](../CONTRACT.md)，关键一条是：

> `success` 表示"拿到了东西"，`completeness` 表示"完整到什么程度"；两者正交。
> **部分内容一律 `success=true` + `completeness=meta`，不会用 `success=false` 表达不完整。**

所以你们**不需要**再为大范围的 `success=false` 兜底；剩下要处理的只是"真的什么都没拿到"
和"需要用户动作"这两类，拿 `error_code` 分流即可。

## 影响面

- 改动点：`VideoMindClient.js` 第 154 行附近的映射逻辑（约 5 行）。
- 风险：低。当前"内容不完整"走 502 会让上层直接失败；改后能降级使用部分内容。
- 建议同时加一条断言：`success=true` 时**不要**因为 `completeness=meta` 抛错。
