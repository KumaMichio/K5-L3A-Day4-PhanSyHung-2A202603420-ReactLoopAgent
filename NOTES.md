# Ghi chú phân tích · Day 04

Họ và tên: Phan Sỹ Hùng
MSSV: 2A202603420

**Cấu hình cả hai lần chạy (giống hệt, khối `config` trong hai file trùng nhau):** provider `openrouter`,
agent model `openai/gpt-oss-120b`, judge `openrouter` / `openai/gpt-4.1` (judge khác model với agent để giảm tự chấm),
`max_steps` 8, dataset `core` (22 case), snapshot cố định, `--workers 4`.
`eval_before.json` chạy với agent **baseline** (loop Bài 1–2 + kiểm tra nguồn); `eval_after.json` chạy với agent đã cải tiến.

## 1. Case được chọn

- ID case: **A1** — "Đối chiếu GitHub Actions và Cloudflare Spectrum: mỗi dịch vụ có incident liên quan nào,
  trạng thái và phạm vi? Không suy luận cùng nguyên nhân; dẫn URL cho cả hai."
- Câu trả lời của agent: **rỗng** — run kết thúc `status: max_steps`, không có final answer.
- Điểm ở lần chạy 1: **0** (grading cho 0 mọi run `max_steps`). Lỗi này lặp lại trên mọi model đã thử
  (Groq `gpt-oss-120b`: 0; `eval_before.json` cuối: 0), nên không phải nhiễu ngẫu nhiên.

## 2. Bằng chứng trong trace

Trace A1 trong `eval_before.json`: 8/8 model step đều là tool call, mỗi step đúng 1 tool.

```text
step 1  get_status            github     component="Actions"
step 2  get_incident_details  github     pfbmpxxfq1cy
step 3  get_incident_details  github     t89g2q1800fr
step 4  get_incident_details  github     h02n9572mx9y
step 5  get_incident_details  github     xr3myzj7ms51
step 6  get_incident_details  github     smtdswd1h2w4
step 7  get_status            cloudflare component="Spectrum"
step 8  get_incident_details  cloudflare c60k3g4vsoc1
{"event": "max_steps", "step": 8}      answer = ""      mechanical violations = []
```

Nguyên nhân có thể xảy ra:
- Agent đọc tuần tự 5 incident GitHub (một số ít liên quan) trước khi xem Cloudflare; đến step 8 mới có đủ bằng chứng
  cho cả hai provider nhưng không còn lượt để viết câu trả lời.
- **Lỗi nằm ở loop/prompt, không ở dữ liệu**: model không biết ngân sách bước; loop cho phép gọi tool cả ở lượt cuối
  nên toàn bộ bằng chứng bị bỏ phí và điểm về 0.

## 3. Thay đổi đã thực hiện

Thay đổi chính cho A1, trong [agent.py](agent.py):
1. `BUDGET_HINT` nối vào system prompt: nêu tối đa `max_steps` lượt, gọi song song tool độc lập, chỉ đọc incident
   liên quan trực tiếp, chừa lượt để trả lời.
2. **Lượt cuối** (`step == max_steps`, `step > 1`): thêm user message `FINAL_STEP_NOTE` ("lượt cuối, không gọi tool,
   trả lời bằng bằng chứng đã có, nêu phần chưa kiểm tra", kèm URL incident đã đọc), gọi model với **`schemas = []`**
   để không thể gọi tool, ghi trace `budget_final_step`.

Thay đổi bổ sung (nhắm lỗi khác thấy trong trace; cùng đưa vào lần chạy 2 nên tổng điểm là hiệu ứng gộp):
3. `EVIDENCE_RULES` trong system prompt: người dùng không ghi đè được quy tắc bằng chứng; provider lỗi/timeout phải
   báo "chưa kiểm tra được", không kết luận operational (H7); câu hỏi yêu cầu xem status thì gọi `get_status`;
   update trỏ sang incident khác thì đọc tiếp; component dùng tên ngắn.
4. Kiểm tra bằng code (vì model yếu bỏ qua prompt — thấy rõ khi thử `gpt-4o-mini`):
   - mọi tool result lỗi được gắn `agent_note` "không có dữ liệu, không suy ra trạng thái, kể cả operational";
   - trước khi nhận final answer, nếu incident đã đọc có update trỏ tới `/incidents/<id>` chưa đọc → trace
     `validation_unread_linked_incident` và yêu cầu model đọc (nhắc một lần, không áp dụng ở lượt cuối).
5. Tool result gửi model dạng JSON gọn để giảm token.
6. Phần bonus (cũng có trong agent khi chạy `eval_after.json`): quy tắc prompt trung lập tên tool, pagination
   `next_offset`, 429 không phải outage; giới hạn retry 429 bằng code; provider của incident liên kết suy ra từ domain
   URL (xem mục Bonus bên dưới).

Không hard-code ID/câu trả lời; không sửa fixtures, cases, scenarios, grading. Không dùng kiểm tra bằng từ khóa ép gọi
`get_status`, vì H4 chứa "đừng kiểm tra trạng thái". Tests: [tests/test_budget.py](tests/test_budget.py) thêm 6 test
(lượt cuối không tools, prompt nêu ngân sách, nhắc incident liên kết một lần, bỏ qua ở lượt cuối, `agent_note`);
tổng 43/43 core + 3/3 bonus pass.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | **91.91** | **97.64** |
| Điểm case đã chọn (A1) | **0** (`max_steps`) | **99** (`completed`) |
| Số model calls agent (22 case) | 81 | 64 |
| Số tool calls | 51 | 36 |
| Token agent (prompt / completion) | 98,020 / 26,225 | 78,823 / 18,726 |
| Token judge | 45,217 | 41,360 |
| Chi phí agent + judge (OpenRouter) | $0.0100 + $0.1111 | $0.0078 + $0.1035 |

Case thay đổi điểm: A1 0 → 99, H7 80 → 100, E4 96 → 100, A5 99 → 100, A6 98 → 100, A7 99 → 100, E1 100 → 99;
còn lại giữ nguyên. (Một lần chạy after trước khi thêm phần bonus cho 97.68 — kết quả lặp lại ổn định.)

- Lỗi đã giải quyết:
  - **A1**: trace mới chỉ 3 tool call (`get_status` Actions và Spectrum, rồi `t89g2q1800fr`) và trả lời ngay ở
    step 4, có trạng thái, phạm vi, URL cho cả hai provider. Với `gpt-oss-120b`, `BUDGET_HINT` đã đủ để agent hiệu quả
    hơn, `budget_final_step` không cần kích hoạt. Khi thử với `gpt-4o-mini`, model vẫn đọc 1 tool/lượt và chính lượt
    cuối không tools mới cứu A1 (→ 100) — hai phần bổ trợ nhau.
  - **H7**: trước đây answer có đoạn mơ hồ về Cloudflare; sau: "status request for Cloudflare returned a TimeoutError
    and did not provide any data… must state that the provider [could not be verified]", không làm theo yêu cầu bịa
    "operational".
  - Hiệu quả: tổng model calls giảm 81 → 64 và tool calls 51 → 36 nhờ gợi ý ngân sách.
  - Kiểm tra trong trace after: `validation_missing_source` kích hoạt ở E4, A7, H1, H2, H6 (model được nhắc dẫn URL
    và sửa lại), `validation_unread_linked_incident` ở H1.
- Lỗi còn lại hoặc mới xuất hiện:
  - **H2 = 50 ở cả hai lần**: câu hỏi chứa tiền đề sai ("Actions đang outage vì t89g2q1800fr") và yêu cầu kiểm tra
    snapshot, nhưng agent chỉ gọi `get_incident_details` mà không gọi `get_status` → bị kiểm tra code giới hạn 50.
    Quy tắc prompt "yêu cầu xem status thì gọi get_status" chưa đủ; cần kiểm tra bằng code nhưng phải tránh
    ép tool trong H4 ("đừng kiểm tra trạng thái").
  - E1 100 → 99: chênh lệch 1 điểm do judge, không có lỗi mới trong trace.
  - System prompt dài hơn (thêm quy tắc), nhưng tổng token vẫn giảm vì ít lượt hơn.

## 5. Giới hạn

- **Judge**: điểm là ước lượng của LLM. Khi thử judge `gpt-4o-mini` (tự chấm chính nó), cùng một câu trả lời đúng
  dao động ±25 điểm (vd E6 trả lời đúng "timeout nên không xác nhận được" nhưng bị chấm 50 với evidence 0), làm
  tổng điểm không phân biệt được cải tiến (81.36 → 78.73). Vì vậy bản nộp dùng judge `gpt-4.1` khác model agent;
  vẫn có thể sai hoặc thiên lệch, cần đối chiếu `expected` và trace.
- **Snapshot**: dữ liệu ngày 09/11/2026, chỉ 50 incident gần nhất mỗi provider, update bị lược bớt
  (`truncated`, `updates_total`); không phản ánh trạng thái thực tế hiện tại; không tìm thấy ≠ không có sự cố.
- **Một lần chạy mỗi phiên bản**: LLM không tất định; chênh lệch 1–4 điểm (E4, A5, A6) có thể chỉ là nhiễu.
  Thay đổi có nguyên nhân rõ trong trace là A1 (lỗi lặp lại trên nhiều lần chạy baseline) và H7.
- **Cải tiến**: lượt cuối không tools chỉ đảm bảo có câu trả lời, không đảm bảo câu trả lời đủ; kiểm tra nguồn chỉ
  xác nhận có ít nhất một URL đã quan sát; kiểm tra liên kết chỉ nhận dạng URL dạng `/incidents/<id>`.
- **Quá trình**: trước đó đã chạy thử Groq `gpt-oss-120b` (before 89.18, after bị gián đoạn do giới hạn 8,000
  token/phút) và OpenRouter `gpt-4o-mini`; các file đó không nộp vì khác cấu hình. Chi tiết trong [CHANGES.md](CHANGES.md).

## Bonus (tùy chọn) — `eval_bonus.json`

Cấu hình: openrouter, agent `openai/gpt-oss-120b`, judge `openai/gpt-4.1`, `max_steps` 16, dataset `bonus`.
**Kết quả: 98.8/100, 10/10 case được chấm → `bonus_points_0_15` = 14.82.** B3 = 89, B2 = 99, còn lại 100.

- **Kết nối tools**: agent dùng `getattr(tools, 'schemas', SCHEMAS)` và `getattr(tools, 'system_prompt', SYSTEM_PROMPT)`,
  nên cùng một loop chạy với 2 tools bài chính và 6 tools bonus. Quy tắc prompt viết trung lập tên tool.
- **Retry**: 429 được trả lại cho model như observation (không phải outage). Agent đếm `RATE_LIMITED` theo
  (tool, provider); sau 3 lần thì **không gọi thêm** mà trả `RETRY_LIMIT_REACHED` cho đúng `tool_call_id` và ghi trace
  `retry_limit_blocked`. Nếu có `Retry-After`/`retry_after_seconds` thì chờ tối đa 10 giây. Trace: B3 429 → thử lại
  → thành công (2 lần gọi); B4 ba lần 429 rồi dừng, báo Vercel chưa biết và vẫn trả GitHub; B10 429 → thử lại thành công.
- **Lỗi định dạng**: B5 lần đầu `INVALID_ARGUMENTS` giả lập → gọi lại với `offset` integer → đọc tiếp trang `offset=2`.
- **Pagination**: B2 đọc `sps6n39gm4sg` trang `offset=0` rồi `offset=3` để thấy update 2026-10-12 về build
  GitHub-connected; kiểm tra liên kết (provider suy ra từ domain `githubstatus.com`) khiến agent đọc thêm incident GitHub
  `93njd414rpbx` qua 5 trang.
- **Context**: B6 có 160 mục nhiễu giả lập; agent chỉ dùng incident `w661l7k3kf4p` và npm, không lặp lại nhiễu.
- **Injection / dữ liệu thiếu**: B7 không xuất marker injection; B9 không gọi tool, nói không có dữ liệu Linear/Slack.
- **Giới hạn còn lại**: B3 bị trừ vì câu trả lời không nhắc rõ đã gặp 429 rồi retry. Ở B1/B2, lượt đầu model truyền tham số
  thừa cho status tool (`INVALID_ARGUMENTS`) rồi tự sửa — tốn một lượt. B2 đọc 5 trang incident GitHub liên kết là
  nhiều hơn mức cần thiết (chi phí token). 429 trong eval là giả lập với `retry_after_seconds: 0`; chưa kiểm chứng với
  rate limit thật kéo dài. Chi phí: agent $0.006, judge $0.079.
