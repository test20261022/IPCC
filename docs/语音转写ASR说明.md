# 语音转写（ASR）说明

> 本文说明：**客服通话录音如何经 ASR 转写成「说话人 + 文本 + 时间戳」的分段消息进入质检**、相关的**技术栈逐项解释**、**阿里云方案的形态与项目当前的真实状态**，并在第四部分列出**面试可能问到的全部问题及答案**。
>
> 事实来源：`backend/app/providers/asr/{base,mock,aliyun}.py`、`backend/app/providers/factory.py`、`backend/app/services/qc/transcribe_service.py`、`backend/app/repositories/qc/conversation_repository.py`、`backend/app/models/qc/conversation.py`、`backend/app/models/qc/enums.py`、`backend/app/utils/async_bridge.py`、`backend/app/api/v1/qc/conversations.py`、`backend/app/core/config.py`、`backend/tests/unit/test_asr_aliyun.py`、`backend/tests/unit/test_providers.py`、`backend/tests/api/test_qc_conversation_crud.py`。
>
> 相关文档：`docs/数据模型与RBAC权限说明.md`、`docs/状态机与并发控制说明.md`、`docs/工程与质量保障说明.md`。

---

## 0. 一分钟速览 + 四条必须说清的事实

| 主题 | 结论 |
|---|---|
| 目标 | 把通话录音变成**对话形式的分段文本**，让质检能判断"客服说了什么 / 客户说了什么" |
| 核心契约 | `AsrSegment(role, text, start_ms, end_ms)` —— **一期就固定**，避免二期返工 |
| 抽象 | `AsrProvider`（ABC）+ `transcribe_segments()` 抽象方法 + `transcribe()` 模板方法 |
| 实现 | `MockAsrProvider`（固定剧本）、`AliyunAsrProvider`（阿里云形态） |
| 切换 | `providers/factory.py::get_asr_provider()` 按 `settings.ASR_PROVIDER`（`.env` 配 `mock` / `aliyun`）选实现 |
| 落库 | 分段消息写入 `qc_messages`（`role` / `start_ms` / `end_ms` / `source=ASR` / `seq`），对话上的 `msg_count` 回填 |
| 状态 | `TranscriptStatus`：`NOT_REQUIRED` / `PENDING` / `RUNNING` / `SUCCESS` / `FAILED` |
| 幂等 | 重转前先 `delete_messages_by_source(conversation_id, ASR)` 清掉旧的 ASR 消息，再按序重写 |
| 接口 | `POST /api/v1/qc/conversations/{id}/transcribe`，权限码 `qc:conversation:transcribe` |

### 四条如实说明（请先读这段）

1. **`AliyunAsrProvider` 目前是"模拟实现"，不发真实请求。** 它 `name = "aliyun"`，且**严格按阿里云「录音文件识别」的调用形态**写成（提交任务 → 轮询结果 → 返回分段），但 `_submit_task` / `_poll_result` 内部是 `uuid` + `asyncio.sleep`，没有 HTTP 调用。源码注释写明了真实接入的改法：

   > 真实接入时只需把 `_submit_task` / `_poll_result` 换成对阿里云 OpenAPI 的 HTTP 调用，分段契约（`AsrSegment`）与日志、异常语义完全复用。

2. **没有独立的 `TRANSITIONS` 状态机。** 项目里外呼任务/坐席/回呼/质检任务/质检明细有 5 张正式流转表，但**转写状态不在这 5 个之内**——它是 `TranscriptStatus` 枚举 + service 里的直接赋值。这与其它 5 个状态机**做法不一致**（详见第 3.1 节）。

3. **"重转清旧消息"的代码已实现，但没有专门的幂等用例。** `_rewrite_asr_messages` → `delete_messages_by_source` 这条链路是存在的，但现有测试**没有**覆盖"同一对话转写两次、断言消息数不翻倍"（详见第 3.2 节与"已知边界"）。

4. **转写是同步阻塞的。** 端点是同步 `def`，Provider 是 async，中间靠 `run_sync` 桥接（在单线程池里跑 `asyncio.run`）。一段 10 分钟的录音会**占住一个请求线程**直到转写完成。没有任务队列（§76 的 MVP 边界）。

另外两条：`ASR_PROVIDER_URL` 配置项**已定义但当前未被使用**（模拟实现不读它）；**没有录音上传接口**（`recording_path` 是调用方传入的路径字符串，§66 只存路径不存二进制）。

---

# 第一部分：ASR 在项目里干什么

## 1.1 为什么不能只返回纯文本

`AsrProvider` 的 docstring 把这个问题讲得最清楚（[base.py#L1-L6](file:///e:/company%20project/backend/app/providers/asr/base.py#L1-L6)）：

> 只返回纯文本会丢失说话人与时间戳，导致质检时无法区分"客服说了什么"与"客户说了什么"。因此一期即固定 `AsrSegment` 契约，真实引擎按同一契约实现，避免二期返工。

质检要评的东西**绝大多数都依赖说话人**：

| 质检项 | 需要的信息 |
|---|---|
| 客服是否使用了规范问候语 | 只看 **AGENT** 的发言 |
| 客服是否抢话 / 打断客户 | 需要 **AGENT 与 CUSTOMER 的时间戳交替关系** |
| 客户情绪是否恶化 | 看 **CUSTOMER** 的语气与用词 |
| 客服是否漏答问题 | 对比 CUSTOMER 的提问与 AGENT 的回应 |
| 静默时长 / 响应速度 | 需要 **start_ms / end_ms** |

如果 ASR 只给一坨纯文本，上面这些**全部做不了**。所以"带上说话人和时间戳"不是锦上添花，而是**质检模块能不能成立的前提**。这也是为什么这个契约要在**一期就固定**——如果一期按纯文本设计，二期要加说话人就得改契约、改 Provider、改落库、改前端、改报表，全链路返工。

## 1.2 端到端链路

```
① 录音落盘（只存路径，§66）
   qc_conversations.recording_path = "qc_conversations/a.wav"
   ↓
② 调接口 POST /qc/conversations/{id}/transcribe  权限：qc:conversation:transcribe
   ↓
③ QcTranscribeService.transcribe()
   ├─ 前置校验：对话存在？channel == VOICE？有 recording_path？
   ├─ transcript_status = RUNNING（先提交，让状态可见）
   ├─ get_asr_provider()  ← 工厂按 .env 选 mock / aliyun
   ├─ run_sync(provider.transcribe_segments(audio_path=绝对路径))
   │     └─ 返回 list[AsrSegment]  每段带 role / text / start_ms / end_ms
   ├─ _rewrite_asr_messages()：删旧 ASR 消息 → 按 seq 批量写新消息
   ├─ transcript_status = SUCCESS，transcript_engine = provider.name
   └─ msg_count = count_messages()
   ↓
④ qc_messages 里出现分段消息（role=AGENT/CUSTOMER、带毫秒时间戳、source=ASR）
   ↓
⑤ 质检工作台按角色与时间轴展示，专家据此打分
```

## 1.3 数据模型

**对话上的 4 个转写相关字段**（[conversation.py#L75-L83](file:///e:/company%20project/backend/app/models/qc/conversation.py#L75-L83)）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `recording_path` | `String(512)` 可空 | 录音路径，**仅存路径不存二进制（§66）** |
| `transcript_status` | 枚举 | `NOT_REQUIRED` / `PENDING` / `RUNNING` / `SUCCESS` / `FAILED` |
| `transcript_engine` | `String(32)` 可空 | **实际使用的转写 Provider 名称**（排障关键：知道这条数据是谁转的） |
| `msg_count` | `Integer` | 消息条数，转写后回填 |

**`qc_messages` 的字段**（[conversation.py#L90-L116](file:///e:/company%20project/backend/app/models/qc/conversation.py#L90-L116)）：

| 字段 | 说明 |
|---|---|
| `seq` | **对话内顺序，从 1 开始**（配合索引 `ix_qc_messages_conversation_seq`） |
| `role` | 说话人：`AGENT`（客服）/ `CUSTOMER`（客户）/ `SYSTEM` |
| `content` | 消息文本 |
| `start_ms` / `end_ms` | **相对对话开始的起止毫秒**（可空——纯文本导入的消息没有时间戳） |
| `source` | 来源：`TEXT`（原始文本）/ `ASR`（语音转写） |

两个设计点值得注意：

- **`start_ms` 用"相对对话开始的毫秒"而不是绝对时间戳**。因为录音本身是一个从 0 开始的时间轴，转写引擎返回的也是相对偏移；存相对值既省空间，又天然不受时区影响。
- **`source` 字段是"重转幂等"的关键抓手**。清旧消息时按 `source = ASR` 删——**只删转写产生的，不动人工录入的 `TEXT` 消息**。这样"人工录入了一段背景说明 + 录音转写"的对话，重转不会把人工部分删掉。

## 1.4 接口与权限

```python
@router.post(
    "/{conversation_id}/transcribe",
    response_model=ApiResponse[TranscribeResultOut],
    summary="对话语音转写",
    description="仅语音对话可转写：清理旧 ASR 消息后写入新的分段消息，失败抛参数错误。",
    dependencies=[Depends(require_permission("qc:conversation:transcribe"))],
)
def transcribe_conversation(conversation_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTranscribeService(db).transcribe(conversation_id))
```

权限码 `qc:conversation:transcribe`（63 个权限码之一）。返回 `TranscribeResultOut`：`conversation_id` / `transcript_status` / `transcript_engine` / `message_count`——**把引擎名和消息数一起返回**，前端不用再查一次就能显示"用 mock 引擎转了 6 条消息"。

---

# 第二部分：技术栈逐项解释

## 2.1 `AsrSegment`：冻结数据类，定死契约

```python
@dataclass(frozen=True)
class AsrSegment:
    """一段转写结果。"""
    role: MessageRole          # AGENT / CUSTOMER / SYSTEM
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
```

| 选择 | 原因 |
|---|---|
| `@dataclass` | 转写结果是**纯数据**，没有行为。用 dataclass 比手写 `__init__` 省事，且 `==` / `repr` 免费得到（测试里直接 `assert first == second` 就是靠它） |
| `frozen=True` | **不可变**。转写结果一旦产出就不该被就地修改（否则"同一个 Provider 两次调用结果不同"的 bug 很难查）。也让它可安全哈希、可跨线程传递 |
| `int \| None` 而非 `int` | 时间戳**允许为空**——纯文本导入的消息、或单声道无分离的降级结果都可能没有精确时间戳。用可空表达"确实没有"比用 `0` 假装有更诚实 |
| `role: MessageRole` | 直接复用 `qc_messages` 的枚举，**不另建一套"说话人"枚举**。避免"Provider 说 SPEAKER_1、数据库说 AGENT"的映射层 |

## 2.2 `AsrProvider`：ABC + 模板方法

```python
class AsrProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def transcribe_segments(self, *, audio_path: str) -> list[AsrSegment]:
        """返回分段转写结果（无内容时返回空列表）。"""

    async def transcribe(self, *, audio_path: str) -> str:
        """整体文本：默认由分段结果拼接，子类一般无需重写。"""
        segments = await self.transcribe_segments(audio_path=audio_path)
        return "\n".join(segment.text for segment in segments if segment.text)
```

三个设计点：

1. **只抽象一个方法**。`transcribe_segments()` 是**必须实现**的（`@abstractmethod`），`transcribe()` 是**模板方法**——默认实现就是"拼接分段"，子类**不需要重写**。这直接体现了"分段才是原始能力，纯文本是派生能力"的判断。测试里专门断言了这两者一致（[test_providers.py#L102-L108](file:///e:/company%20project/backend/tests/unit/test_providers.py#L102-L108)）：

   ```python
   segments = run_sync(asr.transcribe_segments(audio_path="a.wav"))
   # transcribe 默认由分段结果拼接，两者必须一致
   assert run_sync(asr.transcribe(audio_path="a.wav")) == "\n".join(
       segment.text for segment in segments
   )
   ```

2. **`name` 类属性**。每个 Provider 声明自己的名字（`"mock"` / `"aliyun"`），有两个用途：工厂测试断言"默认实现是 mock"（`assert get_asr_provider().name == "mock"`）；**转写成功后写进 `transcript_engine`**——排障时能直接看出"这条数据是哪个引擎转的"。

3. **`async def`**。Provider 接口是 async，因为真实实现要用 `httpx.AsyncClient` 发 HTTP（§29 / §102-14「不阻塞 HTTP」）。这是"为真实实现预留的形状"，不是当前 mock 需要。

4. **`*` 之后的 keyword-only 参数**。`transcribe_segments(audio_path=...)` 强制关键字传参，防止"传了个位置参数其实传错位置"的低级错误。

## 2.3 工厂 + `.env` 切换

[factory.py#L66-L71](file:///e:/company%20project/backend/app/providers/factory.py#L66-L71)：

```python
def get_asr_provider() -> AsrProvider:
    return _resolve(
        settings.ASR_PROVIDER,
        {"mock": MockAsrProvider, "aliyun": AliyunAsrProvider},
        "ASR",
    )()
```

```python
def _resolve(name: str, mapping: dict[str, type], kind: str) -> type:
    provider_cls = mapping.get(name)
    if provider_cls is None:
        raise AppException(f"未知的 {kind} Provider：{name}，可选 {sorted(mapping)}")
    return provider_cls
```

工厂文件的 docstring 给出了**纪律**（[factory.py#L1-L4](file:///e:/company%20project/backend/app/providers/factory.py#L1-L4)）：

> Provider 工厂：按 `.env` 配置选择实现（§68）。
> **Service 层只依赖抽象接口，绝不直接实例化具体 Provider，也不直接发 HTTP。**

| 设计 | 好处 |
|---|---|
| 字典映射 `{"mock": ..., "aliyun": ...}` | 加一个引擎 = 加一行；不用改任何调用方 |
| 未知名字抛 `AppException` **并列出可选值** | 配错 `ASR_PROVIDER=alivun`（拼错）时，报错直接告诉你"可选 ['aliyun', 'mock']"，不用翻代码 |
| Service 只调 `get_asr_provider()` | **service 里没有一句 `if provider == "aliyun"`**，切换引擎零改动 |
| 配置项 `ASR_PROVIDER: str = "mock"` | **默认 mock**——避免开发/CI 环境无意间调到外部付费服务 |

`.env` 三行配置：

```ini
ASR_PROVIDER=mock            # 或 aliyun
ASR_PROVIDER_URL=            # 已定义，当前未使用（见"如实说明 5"）
ASR_PROVIDER_API_KEY=        # 模拟实现只在日志里打印它，用于确认配置已生效
```

> 测试环境在 `conftest.py` 里**强制** `os.environ.setdefault("ASR_PROVIDER", "mock")`，注释写明理由："ASR 演示环境可能配为 aliyun（模拟实现，含轮询延时），测试固定用 mock 保证确定性与速度"。

## 2.4 两个引擎实现

### `MockAsrProvider`（一期默认）

[asr/mock.py](file:///e:/company%20project/backend/app/providers/asr/mock.py) 是**固定剧本**（6 段：客服问候 → 客户咨询 → 客服查询 → 客服答复 → 客户致谢 → 客服收尾），按 `_SCRIPT` 顺序累积时间戳：

```python
cursor = 0
for role, text, duration_ms in _SCRIPT:
    segments.append(AsrSegment(role=role, text=text, start_ms=cursor, end_ms=cursor + duration_ms))
    cursor += duration_ms
```

docstring 说明了定位："一期只要求跑通「录音 → 转写文本 → 质检」链路，故转写内容为确定性假数据，便于前端联调与测试复现"。**"确定性"是关键词**——同一个输入永远得到同一输出，测试才能稳定断言。

### `AliyunAsrProvider`（阿里云形态）

[asr/aliyun.py](file:///e:/company%20project/backend/app/providers/asr/aliyun.py) 比 mock 多做了三件事，都是**为演示真实形态**：

**① 模拟异步任务的两阶段调用**（这是录音文件识别的真实形态）：

```python
task_id = await self._submit_task(audio_path)   # 提交任务，拿 TaskId
await self._poll_result(task_id)                # 轮询
```

注释写明：`_poll_result` 模拟"两次 RUNNING 后 SUCCESS"。

**② 三个台词本 + 按路径哈希选取**：

```python
_SCRIPTS = {"物流咨询": (...), "退款工单": (...), "宽带报修": (...)}

@staticmethod
def _pick_script(audio_path: str) -> str:
    """按录音路径哈希选台词本：同一对话重复转写结果一致（便于演示幂等）。"""
    keys = sorted(_SCRIPTS)
    digest = hashlib.md5(audio_path.encode("utf-8")).hexdigest()
    return keys[int(digest, 16) % len(keys)]
```

用**路径哈希**而不是随机数：同一个录音无论转多少次都得到同一份结果——这样才能演示"重转幂等"。`sorted(keys)` 保证字典序稳定（不依赖 dict 插入顺序）。三个本子覆盖客服场景的不同话术类型。

**③ 两个"看路径就能触发"的演示开关**：

| 开关 | 行为 | 演示什么 |
|---|---|---|
| 路径含 `_fail` | 抛 `RuntimeError("阿里云识别失败：音频格式不支持（StatusCode=41050001）")` | **FAILED 状态**：转写失败时对话状态如何变化、错误如何返回给用户 |
| 路径含 `_mono` | 合并为**单段** `role=SYSTEM` 的消息 | **单声道无说话人分离**的降级：真实场景里如果音频是单声道或引擎不支持分离，只能给一整段文本 |

`_mono` 这个开关很有价值：它演示了**契约的容错能力**——降级后仍然是合法的 `list[AsrSegment]`（只是只有一段、角色是 `SYSTEM`），下游代码一行都不用改。这就是"契约先行"的收益。

## 2.5 阿里云的产品形态（以及本项目的真实状态）

**阿里云智能语音交互（NLS）** 的产品线按"输入方式"分几类：

| 产品 | 输入 | 返回方式 | 适用 |
|---|---|---|---|
| 实时语音识别 | 流式音频（麦克风/实时流） | 边说边返回中间结果 | 实时通话转写 |
| **录音文件识别** | **成段的音频文件** | **异步：提交任务 → 轮询/回调取结果** | **客服通话录音的离线转写（本项目场景）** |
| 录音文件识别（极速版） | 短音频（约 1 分钟内） | 同步返回 | 短语音条 |

本项目对应用**录音文件识别**——因为客服通话是"一通电话结束后拿到一个录音文件"，天然是异步批量场景，不是边打边转。

与质检需求相关的几个能力（**具体参数名请以阿里云官方文档为准**，此处只讲能力层面）：

- **角色分离 / 说话人分离**：把一段双声道或多说话人的录音拆成"谁在第几秒说了什么"。**这正是本项目最依赖的能力**，也是"录音最好是双声道（客服一路、客户一路）"这个建议的来源——双声道时角色判定接近确定，单声道则需要声纹聚类，准确率会下降（这就是 `_mono` 开关演示的情形）。
- **时间戳**：每句返回相对起止时间，直接对应 `AsrSegment.start_ms/end_ms`。
- **标点预测 / 逆文本规整（ITN）**：给文本补标点、把"幺三八"规整成数字等，影响质检关键词匹配的准确率。
- **热词表 / 自定义词表**：加入业务专有名词（产品名、工单类型），提升识别准确率。
- **回调通知**：阿里云支持任务完成后回调你的 URL（而不是一直轮询），本项目当前用的是"轮询"形态。

**本项目当前的真实状态**（务必分清）：

| 环节 | 状态 |
|---|---|
| 分段契约 `AsrSegment` | ✅ 已定稿（role / text / start_ms / end_ms） |
| Provider 抽象 + 工厂 + `.env` 切换 | ✅ 已实现且有测试 |
| 阿里云**调用形态**（提交 → 轮询 → 分段） | ✅ 已按形态实现（模拟） |
| 阿里云**真实 HTTP 调用** | ❌ 未实现（`_submit_task` / `_poll_result` 是 `asyncio.sleep`） |
| 转写状态流转与落库 | ✅ 已实现 |
| 重转清旧消息的幂等代码 | ✅ 已实现（但缺专门用例，见第 3.2 节） |
| 录音上传入口 | ❌ 未实现（`recording_path` 由调用方传入） |
| 异步任务队列（长录音不阻塞请求） | ❌ 未实现 |

**真实接入要改的地方只有两处**（改完其余全部复用）：

```python
async def _submit_task(self, audio_path: str) -> str:
    # 换成：把音频文件 URL 提交给阿里云录音文件识别 OpenAPI，返回 TaskId

async def _poll_result(self, task_id: str) -> dict:
    # 换成：轮询阿里云任务状态，SUCCESS 时拿回带说话人与时间戳的结果
```

同时需要：把音频上传到阿里云可访问的地址（OSS）或使用其"上传录音文件"接口、在配置里填 `ASR_PROVIDER_URL`（当前已定义未使用）、为长任务加回调或任务队列。

**合规备选**：如果数据不能出内网（金融/医疗类客户常见要求），可自建 **FunASR / WhisperX** 等开源引擎，按同一 `AsrSegment` 契约实现一个新的 Provider，在工厂字典里加一行即可——**这就是这层抽象最大的价值：换引擎不改业务代码**。

## 2.6 async 契约 + 同步桥 `run_sync`

这是整个 ASR 链路里**最容易让人困惑**的一处：Provider 是 `async def`，但 service 是同步的、端点是同步的。桥接在 [async_bridge.py](file:///e:/company%20project/backend/app/utils/async_bridge.py)：

```python
def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文执行协程。

    - 当前线程没有事件循环（同步端点 / 定时任务）→ 直接 asyncio.run；
    - 若已在事件循环内（异步端点调用）→ 放到独立线程运行，避免嵌套事件循环。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
```

| 问题 | 答案 |
|---|---|
| 为什么 Provider 要用 async？ | 真实实现要用 `httpx.AsyncClient`；且 §29 定下的接口规范、§102-14 要求"不阻塞 HTTP"。**契约要按真实需要定，不能按 mock 的方便定** |
| 为什么 service 不改成 async？ | service 层是**同步 SQLAlchemy**（全项目统一）。把它改成 async 要连带改 session、repository、所有调用方——为一个 Provider 改造整个数据访问层，不划算 |
| 桥接会不会死锁？ | 不会。**同步上下文**（当前端点是同步 `def`）→ `asyncio.get_running_loop()` 抛 `RuntimeError` → 走 `asyncio.run`，此时当前线程没有事件循环，安全。**已在事件循环内**（比如将来端点改成 async）→ 放独立线程跑，避免 `asyncio.run() cannot be called from a running event loop` |
| 代价是什么？ | 每次调用**起一个线程池 + 一个新事件循环**。对"一次转写一个录音"的调用频率完全可以接受；但**长录音会占住这个线程**直到完成（见"已知边界"） |

注释里还写明了演进路径："本模块把两者隔离在一处，**替换为任务队列时只需改这里**"——这正是"把技术债集中在一个文件里"的典型做法。

## 2.7 落盘策略：只存路径不存二进制（§66）

```python
recording_path: Mapped[str | None] = mapped_column(
    String(512), nullable=True, comment="录音路径，仅存路径不存二进制（§66）"
)
```

数据库里存的是**相对 `STORAGE_DIR` 的路径字符串**（`STORAGE_DIR: str = "storage"`），service 调用时用 `absolute_path()` 拼成绝对路径给 Provider：

```python
segments = run_sync(provider.transcribe_segments(
    audio_path=str(absolute_path(conversation.recording_path))
))
```

| 为什么 | 说明 |
|---|---|
| 数据库不该存大文件 | 一小时通话录音可能几十 MB，放进 PG 会让备份、复制、查询全面变慢（TOAST 也不适合这种量级） |
| 为什么要 `absolute_path()` | Provider 需要能打开的真实路径；而库里存相对路径，方便**整体迁移存储目录**（改 `STORAGE_DIR` 即可，不用更新每行数据） |
| 路径可空 | 纯文本对话没有录音（`recording_path is None`），此时 service 直接拒绝转写 |

---

# 第三部分：转写状态与"重转清旧消息"

## 3.1 状态流转（以及与其它 5 个状态机的差异）

`TranscriptStatus` 的五个值（[enums.py#L31-L38](file:///e:/company%20project/backend/app/models/qc/enums.py#L31-L38)）：`NOT_REQUIRED` / `PENDING` / `RUNNING` / `SUCCESS` / `FAILED`。

**实际流转**（来自全仓库对 `TranscriptStatus.` 的引用点）：

```
                 ┌── 纯文本对话 ──→ NOT_REQUIRED（终态，无需转写）
创建 / 导入 ─────┤
                 └── 语音对话 ────→ PENDING（等转写）
                                       │
                          调转写接口 ↓
                                    RUNNING（先提交，状态可见）
                                       ├── 成功 → SUCCESS
                                       └── 失败 → FAILED
```

| 设置点 | 位置 |
|---|---|
| 创建时按渠道判定 `PENDING` / `NOT_REQUIRED` | [conversation_service.py#L124-L125](file:///e:/company%20project/backend/app/services/qc/conversation_service.py#L124-L125) |
| 导入时按是否带录音判定 `PENDING` / `NOT_REQUIRED` | [conversation_import.py#L614-L615](file:///e:/company%20project/backend/app/services/qc/conversation_import.py#L614-L615) |
| 转写开始 `RUNNING`、成功 `SUCCESS`、失败 `FAILED` | [transcribe_service.py#L39-L56](file:///e:/company%20project/backend/app/services/qc/transcribe_service.py#L39-L56) |

**如实说明：转写状态没有独立的 `TRANSITIONS` 状态机。** 项目里外呼任务、坐席、回呼任务、质检任务、质检明细都有正式的 `XXX_TRANSITIONS` 邻接表 + `ensure_transition` 校验（见 `docs/状态机与并发控制说明.md`），**转写状态不在其列**：它只有枚举，没有流转表，也没有"非法流转"的校验。

这意味着两个差异：
- **好处**：转写状态的合法路径本来就极简（`PENDING → RUNNING → SUCCESS/FAILED`），加一张状态机收益有限。
- **风险**：**可以写出 `SUCCESS → RUNNING` 这种不合理的重转而不被拦截**。当前是靠 service 逻辑约束（谁都不会去改已成功的），不是靠规则拦截。若要做严，可按同样的范式补一个 `TRANSCRIPT_TRANSITIONS` 表 + `ensure_transition`——**这是当前的一个真实一致性缺口**，不是"设计如此"。

**`RUNNING` 为什么"先提交再转写"**：

```python
conversation.transcript_status = TranscriptStatus.RUNNING
self.db.commit()          # ← 先提交，让状态对其它请求可见
provider = get_asr_provider()
try:
    segments = run_sync(...)
except Exception as exc:
    conversation.transcript_status = TranscriptStatus.FAILED
    self.db.commit()
    ...
```

如果先转写再一次性改状态，那么**转写期间（可能几十秒）数据库里还是 `PENDING`**：界面看不出"正在转"，用户会以为没反应重复点；其它人也不知道这条正在被处理。先提交 `RUNNING` 让"进行中"这个状态**可被观察到**。

## 3.2 幂等：重转前先清旧消息

[transcribe_service.py#L73-L94](file:///e:/company%20project/backend/app/services/qc/transcribe_service.py#L73-L94)：

```python
def _rewrite_asr_messages(self, conversation: QcConversation, segments: list[AsrSegment]) -> None:
    """删除旧的 ASR 消息后，按 seq 顺序写入新的转写消息。"""
    self.repo.delete_messages_by_source(conversation.id, MessageSource.ASR)   # ① 先清
    base_seq = self.repo.max_message_seq(conversation.id)                     # ② 取当前最大 seq

    values = [
        {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "seq": base_seq + index,          # ③ 从 max+1 开始重新编号
            "role": segment.role,
            "content": segment.text,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "source": MessageSource.ASR,
        }
        for index, segment in enumerate(segments, start=1)
    ]
    self.repo.bulk_insert_messages(values)                                    # ④ 批量插入
    conversation.msg_count = self.repo.count_messages(conversation.id)        # ⑤ 回填条数
```

四步各有讲究：

**① 先删（按 `source = ASR`）。** 这是幂等的关键。如果不删，重转一次消息就**翻倍**（旧的 6 条 + 新的 6 条 = 12 条），质检专家看到重复台词，报表的"消息数"也失真。按 `source` 删而不是"全删"——**保住人工录入的 `TEXT` 消息**。

**②/③ seq 从"当前最大值 +1"开始递增。** 因为 `qc_messages` 是 **append-only**（表注释："一条消息一行，append-only，不做软删除，同 CallHistory 口径"），`seq` 是"对话内顺序"。用 `max_message_seq` 而不是从 1 重新编号，是为了**不与已有的 `TEXT` 消息冲突**：如果人工先录了 2 条背景说明（seq 1、2），转写消息应该从 3 开始，而不是覆盖 1、2 导致顺序错乱。

```python
def max_message_seq(self, conversation_id: int) -> int:
    stmt = select(func.coalesce(func.max(QcMessage.seq), 0)).where(...)
```

`func.coalesce(func.max(seq), 0)`：没有任何消息时 `max()` 返回 `NULL`，用 `coalesce` 兜成 `0`，于是第一条消息 `seq = 0 + 1 = 1`。**这是"空表首次插入"的必踩点**——不兜的话 `NULL + 1` 还是 `NULL`。

**④ 批量插入而不是逐条 `add`。** `self.db.execute(QcMessage.__table__.insert(), values)` 一条 SQL 插多行。一段 10 分钟通话可能有上百个分段，逐条 `add` 会产生上百次往返。这与质检派发的 `INSERT ... SELECT` 是同一个思路：**能一条 SQL 干完就别循环**。

**⑤ `msg_count` 用 `count(*)` 回填，不是累加 `len(values)`。** 与质检 `total_items` 回填完全同源的理由：**以真实行数为准**，不依赖任何中间返回值。而且它天然处理了"删了旧的又加了新的"这种净变化。

### ⚠️ 如实说明：这条幂等链路缺一个用例

`_rewrite_asr_messages` 的删除逻辑是**存在且正确**的（`delete_messages_by_source` 用 `delete()` + `rowcount` 返回删除条数）。但现有测试覆盖是：

| 已有用例 | 验了什么 |
|---|---|
| `test_transcribe_voice_conversation` | 转写成功 → `SUCCESS` / `engine == "mock"` / `message_count > 0`；再查消息列表，条数一致、**全部 `source == ASR`** |
| `test_transcribe_text_conversation_rejected` | 纯文本对话转写 → 400 / 40001 |
| `test_asr_aliyun.py`（3 个） | 分段确定性与角色/时间戳；`_fail` 抛异常；`_mono` 降级为单段 SYSTEM |
| `test_providers.py` | 工厂默认 mock；`transcribe()` 与分段拼接一致 |

**缺的用例**：对同一语音对话**连续转写两次**，断言：
1. `qc_messages` 总条数**没有翻倍**（等于单次转写的条数）；
2. 旧的 ASR 消息确实被删除（不存在两批 `seq` 重复或断裂）；
3. 若对话先有 `TEXT` 消息，重转后 `TEXT` 消息**仍然存在**。

这三条正是"重转幂等"的核心断言，**当前没有**。代码看起来是对的，但**"看起来对"和"有用例锁住"是两回事**——这是本文档列出的一个真实待补项（见"已知边界"表）。

## 3.3 失败路径

```python
except Exception as exc:  # noqa: BLE001 - 统一转成业务错误
    conversation.transcript_status = TranscriptStatus.FAILED
    self.db.commit()
    logger.exception("对话转写失败：conversation=%s", conversation_id)
    raise ParamError(f"语音转写失败：{exc}") from exc
```

| 处理 | 为什么 |
|---|---|
| 先置 `FAILED` 并提交 | 失败状态必须**落库**——否则界面永远停在 `RUNNING`，用户不知道是失败还是还在转 |
| `logger.exception` 记完整堆栈 | 对排障必需（能看到是阿里云返回了什么、哪一行抛的） |
| `raise ParamError(...)` | 统一转成业务错误 → HTTP 400 / 业务码 **40001**，`message` 里带具体原因（如"阿里云识别失败：音频格式不支持（StatusCode=41050001）"）。**不把内部异常的类名/堆栈直接暴露给用户** |
| `from exc` | 保留异常链，日志里能看到"业务错误由哪个底层异常引起" |
| `# noqa: BLE001` | 显式声明"这里宽泛捕获是故意的"——因为要把**任意引擎异常**统一成业务错误 |

**如实说明**：失败原因**只通过错误消息返回，没有落库**。`qc_conversations` 上没有 `transcript_failure_reason` 字段（只有 `transcript_status` 和 `transcript_engine`）。后果是：**事后无法从数据库查出"这条为什么转写失败"**——只能翻当时的日志。若要做"失败原因列表/批量重试"这类功能，需要补字段。

---

# 第四部分：面试问答

## A. ASR 与语音技术（9 题）

**A1. 为什么 ASR 结果必须带"说话人"？只给文本不够用吗？**

不够用。质检要评的东西**大多依赖说话人**：客服有没有用规范问候语（只看 AGENT）、有没有抢话/打断（需要 AGENT 与 CUSTOMER 时间戳交错）、客户情绪从哪句开始变差（看 CUSTOMER）、客服有没有漏答（对比 CUSTOMER 的问和 AGENT 的答）。只给一坨纯文本，这些**全部做不了**。所以"说话人 + 时间戳"是质检模块成立的前提，不是附加功能。

**A2. 为什么时间戳要存"相对毫秒"而不是绝对时间？**

录音本身是一条**从 0 开始的时间轴**，转写引擎返回的也是相对偏移。存相对值三个好处：① 与引擎输出直接对应，不需要换算；② 不受时区影响（绝对时间就要考虑"用哪个时区解释"，正是报表模块踩过的坑）；③ 与对话的 `started_at` 组合就能还原绝对时间，信息不丢失。

**A3. 双声道和单声道的差别对说话人分离意味着什么？**

双声道（客服一路、客户一路）时，角色判定接近**确定性**——哪一路响就是谁在说，几乎不会错。单声道时引擎只能靠**声纹聚类**猜说话人，遇到音色接近、抢话、背景噪音就可能分错或合并。这就是为什么项目里专门有一个 `_mono` 演示开关：模拟"单声道无说话人分离"时降级成**一整段 `SYSTEM` 消息**。业务建议是**尽量用双声道录音**。

**A4. 说话人分离（speaker diarization）和"角色分离"有什么区别？**

说话人分离是**通用能力**：把音频切成"说话人 A / B / C"，但它不知道 A 是客服还是客户。角色分离是**场景化能力**：直接告诉你哪段是"客服"、哪段是"客户"（通常靠声道信息或业务先验）。本项目的 `AsrSegment.role` 用的是 `AGENT / CUSTOMER / SYSTEM`——**要的是角色而不是说话人编号**。所以接入真实引擎时，如果它只给"说话人 1/2"，就需要一层映射（这一层项目里**还没有**）。

**A5. 时间戳粒度多少合适？为什么用毫秒？**

毫秒（`Integer` 存毫秒数）足够，因为质检关心的最小粒度是"秒级"。用 `int` 毫秒而不是 `float` 秒，是为了**避免浮点误差**（`0.1 + 0.2 != 0.3` 这种问题在累加时间戳时会真实出现）。accumulate 时 `cursor += duration_ms` 用整数加法，结果永远精确。

**A6. 术语解释：ITN 和标点预测对质检有什么影响？**

- **ITN（逆文本规整）**：把口语化的表达规整成书面形式（"幺三八零零" → "13800"、"明天下午两点" → "2026-10-13 14:00"）。有 ITN，关键词/规则匹配才能命中数字与日期。
- **标点预测**：ASR 原始输出通常无标点。没有标点，句子边界无法确定，"客服是否说了完整的一句话"这类规则就无法判断。
- 两者都影响**质检规则的命中率**，属于接入时要确认（并对客户说明）的引擎能力。

**A7. 音频格式/采样率为什么会导致识别失败？**

引擎通常对格式（wav/mp3/双声道）、采样率（8k/16k）、编码有要求。8k 是电话窄带（语音清晰度低、识别率天然低于 16k），格式不符会直接报错。项目里那句模拟错误 `StatusCode=41050001 音频格式不支持` 就是这类失败的形态。**工程上要做的两件事**：接入时明确支持的格式清单；失败时把引擎的原始错误码带回给用户（而不是笼统说"转写失败"）。

**A8. 长录音（如 1 小时）会带来什么问题？**

三处：① **识别耗时**——异步任务可能几分钟才完成，同步等待不现实；② **结果量大**——可能上千个分段，落库要批量写入（项目已用批量插入）；③ **超时**——远超过接口 15 秒超时与 HTTP 网关限制。正确做法是"提交任务 → 回调/轮询 → 后台完成落库"，项目当前是**同步阻塞**的（见 A9 与"已知边界"）。

**A9. 项目里转写是同步还是异步？有什么问题？**

**同步阻塞**：端点是同步 `def`，Provider 是 async，中间靠 `run_sync` 桥接（同步上下文中执行 `asyncio.run`）。问题是一段长录音会**占住一个请求线程直到转完**，并发多个转写请求会耗尽线程池；且客户端可能等到超时。**当前是有意接受的 MVP 边界**（§76），演进方向是把 `run_sync` 这一处替换成任务队列（`async_bridge.py` 的注释就写了"替换为任务队列时只需改这里"）。

## B. 架构与抽象（10 题）

**B1. `AsrProvider` 为什么要定义成抽象基类 + 工厂？不加这层会怎样？**

不加的话，service 里会出现 `if settings.ASR_PROVIDER == "aliyun": ...` 这类分支，而且换引擎时要改**所有调用点**、要 import 具体实现、要处理不同引擎的不同返回结构。加这层之后：service 只依赖 `AsrProvider` 抽象（**一句 `if` 都没有**），换引擎 = 改 `.env` 一行，加引擎 = 工厂字典加一行。这是"依赖倒置"的直接收益。

**B2. 为什么 `name` 放在 Provider 上，而不是从配置读？**

因为**要记录"实际用的是哪个引擎"**。转写成功后写进 `transcript_engine` 字段——排障时能直接看出数据是谁转的。如果从配置读，会出现"配置改了、历史数据的来源记录也跟着变了"的错乱。**用 Provider 自己声明，才是"实际发生的事实"**。

**B3. 为什么 `transcribe()` 是模板方法而不是抽象方法？**

因为"纯文本 = 分段拼接"是**唯一合理的默认实现**，没有引擎会给出不同的拼接规则。做成模板方法（默认实现 + 子类可重写）有两个好处：新 Provider **只需实现一个方法**（降低接入成本）；纯文本与分段**天然一致**（测试里专门断言了两者相等）。如果做成抽象方法，每个 Provider 都得复制一遍拼接代码，早晚有人写出不一致的版本。

**B4. 为什么要用 `@dataclass(frozen=True)`？**

转写结果是**不可变的纯数据**。`frozen=True` 保证"产出的结果不会被就地修改"——否则出现"同一个 Provider 两次调用结果不同"的 bug 时极难查（对象被谁改的？）。另外它还带来免费的可哈希与安全的跨线程传递，`==` 也自动可用（测试里 `assert first == second` 直接比较整个列表）。

**B5. Service 层是同步的、Provider 是 async 的，怎么桥接？为什么这样设计？**

用 `run_sync()`：若当前线程没有事件循环（同步上下文）→ 直接 `asyncio.run`；若已在事件循环内 → 放到**独立线程**里跑，避免 "cannot be called from a running event loop"。这样设计的理由是"两边各自保持最合适的形态"：Provider 用 async 是**为真实实现预留**（真实实现用 `httpx.AsyncClient`，符合 §102-14「不阻塞 HTTP」）；service 保持同步是因为**全项目是同步 SQLAlchemy**，为一个 Provider 把数据访问层改成 async 不划算。桥接集中在一个文件里，将来换任务队列只改这一处。

**B6. 为什么把 `ASR_PROVIDER` 的默认值设成 `mock`？**

安全。默认 `aliyun` 的话，开发/CI 环境一跑就会调外部付费服务（还会因缺 key 报错、产生费用、可能把测试音频传到外部）。默认 mock 是**fail-safe**：不配就用本地假数据，要真引擎必须显式配。测试里还进一步强制 `ASR_PROVIDER=mock`，保证不受环境变量影响。

**B7. 工厂里未知引擎名报错时为什么要列出可选值？**

```python
raise AppException(f"未知的 {kind} Provider：{name}，可选 {sorted(mapping)}")
```

配置拼错（`alivun`）是最常见的低级错误。报错里带上 `可选 ['aliyun', 'mock']`，**用户看到错误就知道怎么改**，不用去翻代码找合法的取值。这是"错误信息产品化"——和状态机 `ensure_transition` 报错里带"当前可流转目标"是同一个思路。

**B8. `AsrSegment` 里的 `start_ms` / `end_ms` 为什么允许为 `None`？**

因为"确实可能没有时间戳"。纯文本导入的消息、单声道降级结果、或某些引擎不返回时间戳。用可空类型表达"确实没有"，比用 `0` 假装有**更诚实**——下游能明确区分"从 0 毫秒开始"和"不知道从多少毫秒开始"。如果强行用 `0` 填充，质检里"响应速度/静默时长"这类指标会算出**错误但看不出来**的数字。

**B9. `_mono` 降级为什么仍然是合法的 `list[AsrSegment]`？这个设计好在哪里？**

因为降级后只是"**只有一段、角色是 `SYSTEM`**"，结构完全不变。所以**下游代码一行都不用改**——service 照样写库、前端照样展示、质检照样能跑（只是失去了角色区分能力）。这就是"契约先行"的收益：**能力降级不会导致链路断裂**。如果当初契约设计成"必须有多段、必须有 AGENT/CUSTOMER"，降级就要走特殊分支，到处都要判断。

**B10. 如果客户要求"数据不能出内网"，这套架构要怎么改？**

**只加一个 Provider，改一行配置**。按同一个 `AsrSegment` 契约实现自建引擎（FunASR / WhisperX 等）的 `LocalAsrProvider`，在工厂字典里加 `{"local": LocalAsrProvider}`，`.env` 改成 `ASR_PROVIDER=local`。service、落库、接口、前端、质检逻辑**全部不动**。这正是这层抽象的**最大价值所在**——不是为了"代码好看"，而是为了"换引擎不改业务代码"。当然前提是自建引擎要能输出**说话人与时间戳**（WhisperX 有 diarization 能力）。

## C. 状态、幂等与数据（9 题）

**C1. 转写状态有哪些？完整流转是什么？**

`NOT_REQUIRED`（纯文本对话，无需转写）/ `PENDING`（语音对话，等转写）/ `RUNNING` / `SUCCESS` / `FAILED`。创建或导入时按"是否语音、是否带录音"置 `PENDING` 或 `NOT_REQUIRED`；调转写接口时 `PENDING → RUNNING`，成功 `→ SUCCESS`，失败 `→ FAILED`。

**C2. 为什么要在转写**开始前**就把状态置为 `RUNNING` 并提交？**

因为转写要花时间（真实引擎可能几十秒到几分钟）。如果等转完再一次性写状态，那么**转写期间数据库里还是 `PENDING`**：界面看不出"正在转"，用户以为没反应会重复点；其它人也无法知道这条正被处理。先提交 `RUNNING`，让"进行中"这个状态**可被观察到**——这是"状态可见性"的基本要求。

**C3. 转写失败为什么要落库 `FAILED` 而不是直接抛错就完？**

不落库的话，状态会**永久停在 `RUNNING`**——用户分不清是"还在转"还是"已经失败"。必须把失败**持久化成可查询的状态**，界面才能显示"转写失败，可重试"。同时用 `logger.exception` 留下完整堆栈供排障，再用 `ParamError` 把**面向用户的错误信息**（含引擎错误码）返回。

**C4. "重转幂等"是怎么实现的？**

`_rewrite_asr_messages` 的第一步是 `delete_messages_by_source(conversation_id, MessageSource.ASR)`——**先把旧的 ASR 消息删干净，再写新的**。所以无论转多少次，最终结果都只有"最新一次"的那批消息，数量不会累加。注意是**按 `source = ASR` 删**，不是删全部：人工录入的 `TEXT` 消息会被保住。

**C5. 清旧消息为什么要按 `source` 过滤，而不是"删掉这个对话的所有消息"？**

因为一个对话的消息可能**有两种来源**：人工录入的 `TEXT` 和语音转写的 `ASR`。全删会把人工录入的背景说明、补充信息也删掉——**数据丢失且不可恢复**。按来源过滤是"只清自己产生的那部分"，这是幂等操作该有的边界意识：**只回滚自己做的事**。

**C6. `seq` 为什么从"当前最大值 + 1"开始，而不是从 1 重新编号？**

因为 `qc_messages` 是 **append-only** 的（不做软删除），`seq` 表示"对话内顺序"。如果人工先录了 2 条说明（seq 1、2），转写消息又从 1 开始编号，就会**与已有消息撞号**，按 `seq` 排序出来的对话顺序会完全错乱。用 `max + 1` 保证新消息**永远排在后面**。

**C7. `coalesce(max(seq), 0)` 里的 `coalesce` 是干什么的？**

空表（没有任何消息）时 `max(seq)` 返回 `NULL`，`NULL + 1` 还是 `NULL`，第一条消息的 `seq` 就会是 `NULL`，而 `seq` 是 `NOT NULL` 列 → 直接报错。用 `coalesce(..., 0)` 把 `NULL` 兜成 `0`，于是第一条消息 `seq = 0 + 1 = 1`。**这是"首次插入"的必踩点**。

**C8. `msg_count` 为什么用 `count(*)` 回填而不是 `len(values)`？**

因为 `len(values)` 只是"这次插了多少条"，而对话的总消息数还包括 `TEXT` 消息。而且 `count(*)` **以数据库真实行数为准**，不依赖任何中间返回值——重转（删旧的 + 加新的）这种净变化也能自动算对。与质检 `total_items` 用 `count(*)` 回填是同一个原则。

**C9. 项目里转写状态有正式的状态机吗？**

**没有**（如实说明）。项目里外呼任务、坐席、回呼任务、质检任务、质检明细都有正式的 `TRANSITIONS` 邻接表 + `ensure_transition` 校验，但转写状态只有枚举 + service 里的直接赋值，**没有流转表、没有非法流转校验**。转写路径本来就极简（`PENDING → RUNNING → SUCCESS/FAILED`），加状态机收益有限；但代价是**可以写出 `SUCCESS → RUNNING` 这种不合理重转而不被规则拦住**。要做严，按同样范式补一张 `TRANSCRIPT_TRANSITIONS` 即可。**这是当前的一个一致性缺口，不是设计如此。**

## D. 阿里云接入实操（8 题）

**D1. 为什么选阿里云的录音文件识别，而不是实时语音识别？**

因为场景是**"一通电话结束后拿到一个录音文件"**，天然是离线的批处理，不是"边说边转"。实时语音识别用于流式场景（坐席辅助、实时质检预警），本项目一期做的是**事后质检**，所以用**录音文件识别**——它按"提交任务 → 轮询/回调取结果"的异步形态工作，适合成段音频。

**D2. 录音文件识别的调用流程是怎样的？**

三步：① **提交任务**——把音频地址（通常是 OSS URL）与参数（是否开说话人分离、采样率、热词表等）提交给接口，得到一个 `TaskId`；② **等待完成**——任务在云端异步跑（可能几十秒到几分钟），通过**轮询状态**或**配置回调 URL** 得知完成；③ **取结果**——拿到带说话人、文本、时间戳的识别结果。项目的 `AliyunAsrProvider` 就是按这个形态写的（`_submit_task` → `_poll_result` → 组织分段）。

**D3. 项目里真的调了阿里云吗？**

**没有**（如实说明）。当前 `AliyunAsrProvider` 是**模拟实现**：`name = "aliyun"`、按阿里云调用形态组织代码，但 `_submit_task` 返回 `uuid` 拼的假 TaskId、`_poll_result` 只是 `asyncio.sleep` 两次再返回。**真实接入只需替换这两个方法**为对阿里云 OpenAPI 的 HTTP 调用，`AsrSegment` 契约、日志、异常语义**完全复用**。这样做的价值是：**接入路径已经验证过了**（分段怎么组织、时间戳怎么算、降级怎么做），真实接入是"填两个方法"而不是"重新设计"。

**D4. 真实接入还需要补哪些东西？**

除了那两个方法，还有四件：① **音频要能被阿里云访问**——上传到 OSS 或使用其录音上传接口，不能用本地路径（当前 `absolute_path()` 给的是**本地**绝对路径，真实接入要改成可访问的 URL）；② **填 `ASR_PROVIDER_URL`**（配置项已定义但当前未使用）；③ **长任务的异步化**——改成回调或任务队列，否则请求线程会被占住；④ **网络异常的容错**——超时、重试、限流（可复用 `PROVIDER_TIMEOUT_SECONDS` / `PROVIDER_MAX_RETRIES` 的既有模式，呼叫网关 Provider 已有先例）。

**D5. 如果阿里云只返回"说话人 1 / 说话人 2"，怎么映射成客服和客户？**

三种策略（按可靠性排序）：① **双声道优先**——声道 1 = 客服、声道 2 = 客户（最可靠，接入时应尽量要求双声道录音）；② **首句规则**——客服通常先说"您好，很高兴为您服务"，可用首段说话人判定为 AGENT 并推出另一个是 CUSTOMER（简单但可能被异常开场打破）；③ **业务先验**——结合录音来自"外呼坐席端"这个事实（坐席端录音的第一个说话人大多是坐席）。**如实说明**：项目里**还没有**这层映射——因为模拟实现直接产出 `AGENT`/`CUSTOMER`。真实接入时这是**必须补的一环**，也是前面提过的那个缺口。

**D6. 为什么建议双声道录音？**

因为双声道让"谁在说"变成**确定性问题**而不是概率问题：客服与客户各占一路，哪一路有声音就是谁在说，不需要声纹聚类，也不可能混淆。单声道只能靠声纹猜，遇到音色接近、抢话、噪音就会出错（项目用 `_mono` 开关演示了这种降级）。

**D7. 热词表（自定义词表）有什么用？为什么质检场景需要？**

客服通话里有大量**业务专有名词**：产品名、套餐名、工单类型、内部术语。通用模型对这些词的识别率往往不高，识别错了会导致质检规则**误判**（比如"退款"识别成"退宽"，规则就匹配不上）。热词表就是把这些词喂给引擎提升识别率。**质检规则越依赖关键词，热词表越重要**。

**D8. 如果客户要求数据不出内网，怎么办？**

换成**自建开源引擎**（FunASR / WhisperX 等），按同一个 `AsrSegment` 契约实现 `LocalAsrProvider`，工厂字典加一行、`.env` 改一行即可，**业务代码零改动**（详见 B10）。要注意的取舍：① 需要能输出**说话人分离**（WhisperX 具备 diarization，需要额外的声纹模型）；② 要有 GPU 资源与运维投入；③ 识别准确率与阿里云相比需要实测评估（尤其方言、噪音场景）。**这是"抽象层"的存在意义被真正兑现的场景**。

---

# 附：自行复核（命令清单）

```bash
cd backend

# ① 分段契约与抽象（看 role/text/start_ms/end_ms 四个字段）
cat app/providers/asr/base.py

# ② 工厂与 .env 切换（ASR_PROVIDER 的取值与默认值）
grep -n "ASR" app/providers/factory.py app/core/config.py

# ③ 两个引擎实现（确认 aliyun 是模拟：_submit_task 里有没有真实 HTTP）
grep -n "sleep\|uuid\|httpx\|_fail\|_mono" app/providers/asr/aliyun.py

# ④ 转写服务：状态流转 + 重转清旧消息
grep -n "transcript_status\|delete_messages_by_source\|max_message_seq\|bulk_insert" \
  app/services/qc/transcribe_service.py

# ⑤ 状态的实际设置点（全仓库）
grep -rn "TranscriptStatus\." app/ | grep -v enums.py

# ⑥ ASR 相关测试
python -m pytest tests/unit/test_asr_aliyun.py tests/unit/test_providers.py -v
python -m pytest tests/api/test_qc_conversation_crud.py -k transcribe -v

# ⑦ 验证"重转幂等"缺口：目前没有任何用例覆盖同一对话转写两次
grep -rn "transcribe" tests/ | grep -c "两次\|twice\|repeat"
```

```powershell
# ⑧ 确认没有录音上传接口（只有对话文件导入与名单导入用 UploadFile）
Select-String -Path app/api/v1 -Recurse -Pattern "UploadFile"
```

# 附：已知边界（如实记录）

| # | 边界 | 现状 | 影响 / 补齐方式 |
|---|---|---|---|
| 1 | **阿里云是模拟实现** | `_submit_task` / `_poll_result` 是 `uuid` + `asyncio.sleep`，无 HTTP | 真实接入只需替换这两个方法（详见 D3/D4） |
| 2 | **无"说话人 → 角色"映射层** | 模拟实现直接产出 `AGENT`/`CUSTOMER` | 真实引擎若只给"说话人 1/2"，必须补映射（详见 D5） |
| 3 | **重转幂等缺专门用例** | 删除逻辑已实现（`delete_messages_by_source`），但无用例断言"转两次消息数不翻倍" | 补 3 条断言：总数不翻倍、旧 ASR 已删、`TEXT` 消息仍存在（详见 3.2 节） |
| 4 | **转写状态无正式状态机** | 只有 `TranscriptStatus` 枚举 + service 直接赋值 | 可写出 `SUCCESS → RUNNING` 不被拦截；可按同样范式补 `TRANSCRIPT_TRANSITIONS` |
| 5 | **同步阻塞** | 同步端点 + `run_sync` 在单线程池跑 `asyncio.run` | 长录音占住请求线程；演进方向是任务队列（`async_bridge.py` 已预留"只改这里"） |
| 6 | **失败原因未落库** | 只有 `transcript_status` / `transcript_engine`，无 `transcript_failure_reason` | 事后无法从库里查"为什么失败"，只能翻日志；做"失败列表/批量重试"需补字段 |
| 7 | **无录音上传入口** | `recording_path` 由调用方传入路径字符串 | 真实使用需补上传接口（或对接 OSS/对象存储） |
| 8 | **`ASR_PROVIDER_URL` 未使用** | 配置项已定义，模拟实现不读它 | 真实接入时启用（详见 D4） |
| 9 | **轮询无重试/限流** | `_poll_result` 是写死的两次循环 | 真实接入需补超时、重试、限流（可参考呼叫网关 Provider 的既有模式） |
| 10 | **只支持单文件转写** | 一次接口调用转一段录音 | 批量转写（多对话批量提交）未实现 |