# SDK 认证熔断测试文档

## 1. 测试目标

验证 `HpsiMcpClient` 在认证或支付配置无效时能够及时熔断，避免同一个 Client 持续向服务端发送重复的 `401`/`402` 请求。

验收标准：

- 当前 Client 第一次收到未解决的 HTTP `401` 或 `402` 后抛出 `HpsiMcpConfigError`。
- 熔断后，当前 Client 的后续 SDK 调用不发送 HTTP 请求，直接在本地抛出 `HpsiMcpConfigError`。
- 调用 `set_api_key()`、`set_wallet()` 或创建新 Client 后可以恢复请求。
- 没有可用 x402 Wallet 时，`402` 绝不自动重试。
- 有可用 x402 Wallet 时，只允许签名并重试一次。
- 并发调用不能绕过熔断状态。
- `403`、`429` 和其他非认证错误继续保持原有异常行为，不错误触发认证熔断。

## 2. 测试环境

- Python 3.9 或更高版本
- SDK 源码目录：`hpsilab-mcp-sdk`
- 已安装开发依赖及 `pytest`

在 PowerShell 中运行完整测试：

```powershell
cd E:\apps\quantum_app\hpsilab-mcp-sdk
$env:PYTHONPATH = "src"
python -m pytest -q -p no:cacheprovider
```

预期结果：

```text
57 passed
```

只运行熔断相关测试：

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q -p no:cacheprovider `
  tests/test_client.py `
  tests/test_payments.py `
  tests/test_resend_verification.py
```

## 3. 自动化测试用例

### TC-01：401 首次触发熔断

前置条件：Client 配置一个无效 API Key，Mock 服务第一次返回 `401`。

步骤：

1. 调用任意 SDK 方法。
2. 捕获异常。
3. 再调用另一个 SDK 方法。
4. 统计 Mock Transport 收到的请求数。

预期结果：

- 第一次调用抛出 `HpsiMcpConfigError`，错误中包含 `HTTP 401` 和服务端错误信息。
- 第二次调用也抛出 `HpsiMcpConfigError`。
- Transport 总共只收到 1 个请求。

对应测试：`tests/test_client.py::HpsiMcpClientTests::test_auth_circuit_blocks_later_calls_until_api_key_is_reconfigured`

### TC-02：无 Wallet 的 402 首次触发熔断

前置条件：Client 有 API Key，但没有 x402 Wallet；服务端返回 `402`。

步骤：

1. 调用付费或超额工具。
2. 再调用任意其他工具。
3. 统计请求数。

预期结果：

- 第一次调用不重试，直接抛出 `HpsiMcpConfigError`。
- 后续调用在本地失败。
- 服务端总共只收到 1 个请求。

对应测试：`tests/test_payments.py::PaymentFlowTests::test_final_402_trips_breaker_and_blocks_all_later_requests`

### TC-03：可用 Wallet 完成一次 x402 重试

前置条件：Client 配置可用 Wallet；第一次响应为 `402`，支付后的响应为 `200`。

预期结果：

- Wallet 的 `payment_headers()` 只调用一次。
- 第一个请求不带支付签名。
- 第二个请求携带支付签名。
- SDK 返回第二个请求的成功响应。
- Client 不进入熔断状态。

对应测试：`tests/test_payments.py::PaymentFlowTests::test_wallet_pays_and_the_retry_carries_the_payment_header`

### TC-04：Wallet 重试后仍返回 402

前置条件：Client 配置 Wallet；原始请求和支付重试都返回 `402`。

预期结果：

- 总共只执行原始请求和一次支付重试。
- Wallet 只签名一次，不产生循环扣款。
- 最终抛出 `HpsiMcpConfigError` 并熔断 Client。
- 再次调用时不发送新请求。

### TC-05：Wallet 无法生成支付签名

前置条件：Wallet 的 `payment_headers()` 抛出异常或无法生成有效 Headers。

预期结果：

- 不发送支付重试请求。
- Client 抛出 `HpsiMcpConfigError` 并熔断。
- Wallet 原始异常保留在 `HpsiMcpConfigError.__cause__` 中，便于排查。

对应测试：`tests/test_payments.py::PaymentFlowTests::test_a_refused_challenge_propagates_untouched`

### TC-06：重新配置 API Key 后恢复

步骤：

1. 使用无效 Key 触发一次 `401`。
2. 验证下一次调用没有发送请求。
3. 调用 `client.set_api_key("hpsi_valid_key")`。
4. 再次调用 SDK 方法。

预期结果：

- `set_api_key()` 清除熔断状态并更新 `Authorization` Header。
- 后续调用恢复发送请求。
- 请求使用新的 API Key。

### TC-07：重新配置 Wallet 后恢复

步骤：

1. 触发 `401` 或未解决的 `402`。
2. 调用 `client.set_wallet(valid_wallet)`。
3. 再次调用 SDK 方法。

预期结果：

- 熔断状态被清除。
- 后续请求可以正常发送。
- 如果再次收到 `402`，仅执行一次 Wallet 支付重试。

### TC-08：拒绝清空唯一认证方式

测试以下两种情况：

- Client 没有 Wallet 时调用 `set_api_key(None)`。
- Client 没有 API Key 时调用 `set_wallet(None)`。

预期结果：

- 抛出 `HpsiMcpConfigError`。
- Client 不会恢复为无认证但可发送请求的状态。

### TC-09：并发调用

前置条件：多个线程共享同一个 Client，服务端返回 `401`。

步骤：使用线程池同时调用多个 SDK 方法，并统计 Transport 请求数。

预期结果：

- 第一个到达服务端的请求收到 `401` 并触发熔断。
- 等待实例锁的其他调用随后在本地失败。
- 服务端只收到 1 个请求。
- 所有调用均得到 `HpsiMcpConfigError`，不得发生死锁。

## 4. 非回归测试

| 响应 | 预期异常/行为 | 是否熔断 |
|---|---|---:|
| 200–399 | 正常解析并返回 | 否 |
| 400 | `HpsiMcpAPIError` | 否 |
| 401 | `HpsiMcpConfigError` | 是 |
| 402，无可用 Wallet | `HpsiMcpConfigError`，不重试 | 是 |
| 402，有可用 Wallet | 最多支付重试一次 | 仅最终仍失败时 |
| 403 | 保持 `HpsiMcpAuthError` | 否 |
| 429 | 保持 `HpsiMcpRateLimitError` | 否 |
| 500 | `HpsiMcpAPIError` | 否 |
| 网络超时 | `HpsiMcpTimeoutError` | 否 |
| 连接失败 | `HpsiMcpConnectionError` | 否 |

## 5. 线上验证建议

线上验证应使用专门测试 Key，避免影响真实用户：

1. 使用确定无效的测试 Key 创建一个 Client。
2. 连续调用同一工具 5 次。
3. 第一次及后续调用都应在调用端看到 `HpsiMcpConfigError`。
4. 在 `/manage/request-logs` 按 API Key ID、IP、SDK Client 和时间范围过滤。
5. 确认该 Client 只产生 1 条 `401` 记录。
6. 调用 `set_api_key()` 配置有效测试 Key，再调用一次。
7. 确认请求恢复并产生正常的成功日志。

不要在线上使用真实资金 Wallet 测试持续 `402`；支付路径优先通过 `httpx.MockTransport` 验证。

## 6. 通过标准

- 所有自动化测试通过。
- 401/无 Wallet 402 的重复调用场景中，服务端请求计数严格为 1。
- 有 Wallet 时最多进行一次支付重试。
- 重新配置认证后请求正常恢复。
- 其他 HTTP 和网络异常的原有行为没有变化。
