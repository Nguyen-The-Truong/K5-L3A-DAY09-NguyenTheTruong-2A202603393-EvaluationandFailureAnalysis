# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

Hai judge được replay từ CSV (không gọi model). FAIL là lớp dương: việc của judge là **tìm** reply tệ.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | **Đạt** cả 3 | **Dùng**, chỉ cho giọng văn |
| helpful (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | 0.300 | **Trượt** κ và recall | **Loại**, không dùng làm gate |

Ma trận nhầm lẫn (người × judge, FAIL = dương):

| | tp | fp | fn | tn | Tỉ lệ FAIL quan sát | Sau Rogan-Gladen |
|---|---:|---:|---:|---:|---:|---:|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

## ≥5 case audit thủ công

Dưới đây là 10 bất đồng của `tone_ok` (toàn bộ) và 3 case tiêu biểu của `helpful`. Cột "Ai đúng?" là kết luận sau khi đọc lại câu trả lời, dùng ghi chú của người gán nhãn làm căn cứ.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã; judge nhầm suồng sã với thân thiện. **Sửa rubric:** cấm đại từ/trợ từ suồng sã với khách (`bạn`, `nha`, `nhé`, `nè`); thêm 2 ví dụ FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Gọi khách là "bạn", cùng lỗi với #1. **Sửa rubric:** khách phải được gọi là "anh/chị". |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh; judge chỉ thấy "Dạ, vui lòng". **Sửa rubric:** FAIL nếu có mệnh lệnh phủ định gửi khách ("không cần…", "đừng…"). |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì thiếu xin lỗi. **Sửa rubric:** lời xin lỗi **không bắt buộc**, chỉ cần khi đơn trễ hoặc khách khiếu nại. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | "refund" là thuật ngữ CS được LogiX cho phép; judge phạt vì tiếng Anh. **Sửa rubric:** thêm danh sách thuật ngữ được phép (`refund`, `ledger`…). |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống; judge không biết ledger. Đây thực chất là lỗi thông tin, không phải giọng văn. **Sửa rubric:** loại khỏi `tone_ok`, chuyển sang kiểm bằng code (cam kết ngoài ledger). |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji không hợp ngữ cảnh khiếu nại. **Sửa rubric:** cấm emoji trong reply gửi khách. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú của chính người gán nhãn: "đọc nhầm ticket, judge đúng, sửa nhãn". **Hành động:** sửa **nhãn người**, không sửa judge. Nếu sửa H-081 thành FAIL thì P=0.893, R=0.806, κ=0.784 (số cũ: 0.857 / 0.800 / 0.757). Kết luận quyết định không đổi. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Người (còn tranh cãi) | Lặp "Dạ" là lỗi gõ chứ không phải giọng văn. **Sửa rubric:** tách "lỗi chính tả/định dạng" khỏi `tone_ok` để judge không phạt nhầm. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | Người | Dịch máy, mất dấu tiếng Việt. **Sửa rubric:** FAIL nếu mất dấu tiếng Việt. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger ghi 40.000đ) | PASS | FAIL | Người | Reply nói 55.000đ, ledger giữ 40.000đ. Judge không nhìn thấy ledger nên không thể biết. Đây là **FM-08**, phải chấm bằng code. |
| 12 | HL-016 (xin lỗi dài dòng, nói 55.000đ, ledger ghi 35.000đ) | PASS | FAIL | Người | Câu xin lỗi trơn tru lấp đi việc sai số tiền; judge bị văn phong đánh lừa. |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không có số tiền, giọng suồng sã. Code không bắt được; cần rubric tone (xem #1–2). |

## Kết luận

**Tiêu chí bị loại: `helpful`.** Ma trận nhầm lẫn là tp=9, fp=0, fn=21, tn=70.
- Precision 1.0 trông tốt nhưng vô nghĩa: judge gần như không bao giờ nói FAIL, nên khi nói thì đúng. Recall chỉ 0.3 (dưới sàn 0.7) và κ 0.375 (dưới sàn 0.6).
- Judge bỏ sót **21/30** reply mà người gán FAIL, và cả 21 đều là âm tính giả (judge PASS, người FAIL). Một gate dùng judge này cho qua khoảng 70% reply tệ.
- Rogan-Gladen cho thấy hậu quả: tỉ lệ FAIL quan sát 0.09, sau hiệu chỉnh 0.30. Judge che giấu hai phần ba số lỗi.
- Nguyên nhân gốc: 18/21 bỏ sót có ghi chú "ledger ghi X", tức reply nói số tiền khác ledger. Judge không đọc ledger nên không thể biết. Lỗi này kiểm tra được bằng code: grader `reply_matches_ledger` (FM-08, `lab9/graders.py`) áp lên 18 case này bắt được **18/18**. Tiền luôn chấm bằng code, không dùng judge.
- 3 bỏ sót còn lại (HL-047, HL-091, HL-097, "Ok bạn… xử lý rồi nhé") không có số tiền nên code không bắt được. Đó là lỗi giọng văn và thuộc về `tone_ok`.

**Tiêu chí được dùng: `tone_ok`**, đạt cả ba sàn (κ 0.757, P 0.857, R 0.800). Chỉ dùng cho giọng văn, không dùng cho số tiền, approval hay secret. Vẫn nên sửa rubric theo mục 1–10 ở trên vì 9/10 bất đồng đến từ rubric chưa nêu rõ quy tắc (đại từ, lệnh, emoji, thuật ngữ, dấu tiếng Việt, xin lỗi, lỗi gõ; riêng #6 phải chuyển sang kiểm bằng code) và 1/10 (#8) do nhãn người sai. Không có case nào cho thấy riêng judge kém.

**Rủi ro còn lại:**
- Judge chỉ được kiểm trên dữ liệu replay đã công khai (100 mẫu mỗi bộ); cần nhãn người mới, chưa từng lộ, để có held-out thật.
- Một nhãn người đã sai (H-081), nên nhãn người cũng cần được audit, không mặc định là chân lý. Mình chưa sửa file CSV; số liệu sửa nhãn ở trên chỉ là phân tích độ nhạy.
- Cột "Ai đúng?" là đánh giá của người làm audit, dựa trên ghi chú có sẵn trong CSV, chưa có người thứ hai xác nhận độc lập.
