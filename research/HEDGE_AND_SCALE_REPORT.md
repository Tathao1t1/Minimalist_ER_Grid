# Báo cáo Thử nghiệm: Phòng vệ Hàng tồn Phái sinh (VN30F) & Tối ưu Scale Vốn

Dựa trên phản hồi và gợi ý của Advisor:
1. **Short phái sinh theo giá trị hàng tồn:** Tích lũy hàng tồn càng nhiều thì short càng nhiều, không cần đoán đỉnh đáy.
2. **Thử nghiệm scale vốn:** 500 triệu, 1 tỷ và 5 tỷ VND.
3. **Tối ưu bước grid:** Nâng số cấp grid (N = 18, 24, 30, 36) để tối ưu hiệu suất sử dụng vốn.

![Inventory Hedge Comparison](images/inventory_hedge_scale_comparison.png)

## 1. So sánh Hiệu quả Phòng vệ Hàng tồn (Vốn 1.0 Tỷ, N=18)

| Giai đoạn Thị trường | Chế độ Giao dịch | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Roundtrips Khớp | PnL Harvest Cơ sở | PnL Phái sinh VN30F |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| in_sample | Unhedged (Pure Spot Grid) | -4.65% | -32.46% | 0.092 | 851 | +251,394,612 VND | +0 VND |
| in_sample | Dynamic Inventory Hedge (VN30F) | +3.90% | -32.92% | 0.125 | 851 | +251,394,612 VND | +85,550,000 VND |
| out_sample | Unhedged (Pure Spot Grid) | +12.47% | -6.54% | 0.302 | 342 | +137,275,020 VND | +0 VND |
| out_sample | Dynamic Inventory Hedge (VN30F) | +9.19% | -6.95% | 0.126 | 342 | +137,275,020 VND | -32,870,000 VND |
| holdout | Unhedged (Pure Spot Grid) | +1.34% | -45.24% | 0.386 | 474 | +171,506,277 VND | +0 VND |
| holdout | Dynamic Inventory Hedge (VN30F) | +0.18% | -41.59% | 0.359 | 474 | +171,506,277 VND | -11,580,000 VND |

## 2. Thử nghiệm Scale Vốn (500M, 1B, 5B VND)

| Quy mô Vốn | Giai đoạn | Lợi nhuận (HPR) | Max Drawdown | Sharpe (Rf=6%) | Tỷ lệ Vi phạm Lot 100 CP | PnL Harvest | PnL Phái sinh |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 500M VND | in_sample | -4.12% | -32.08% | 0.089 | 0.0% | +124,937,724 VND | +910,000 VND |
| 500M VND | holdout | +0.29% | -44.03% | 0.386 | 0.0% | +86,132,936 VND | -6,980,000 VND |
| 1.0B VND | in_sample | +3.90% | -32.92% | 0.125 | 0.0% | +251,394,612 VND | +85,550,000 VND |
| 1.0B VND | holdout | +0.18% | -41.59% | 0.359 | 0.0% | +171,506,277 VND | -11,580,000 VND |
| 5.0B VND | in_sample | +3.21% | -31.65% | 0.112 | 0.0% | +1,263,486,258 VND | +378,280,000 VND |
| 5.0B VND | holdout | -0.82% | -42.91% | 0.357 | 0.0% | +860,939,564 VND | -101,950,000 VND |

## 3. Thử nghiệm Tối ưu Số bước Grid (N = 18, 24, 30, 36)

| Quy mô Vốn | Số bước (N) | Spacing (%) | In-Sample Return | In-Sample MaxDD | Holdout Return | Holdout MaxDD | Holdout Roundtrips |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1.0B VND | 18 | 1.8% | +3.90% | -32.92% | +0.18% | -41.59% | 474 |
| 1.0B VND | 24 | 1.5% | +7.15% | -35.05% | -1.14% | -38.06% | 611 |
| 1.0B VND | 30 | 1.5% | +4.69% | -27.52% | -2.81% | -30.16% | 611 |
| 1.0B VND | 36 | 1.5% | +4.03% | -24.67% | +0.72% | -26.54% | 611 |
| 5.0B VND | 18 | 1.8% | +3.21% | -31.65% | -0.82% | -42.91% | 474 |
| 5.0B VND | 24 | 1.5% | +5.85% | -35.06% | -1.53% | -38.39% | 611 |
| 5.0B VND | 30 | 1.5% | +5.47% | -28.20% | -1.31% | -30.79% | 611 |
| 5.0B VND | 36 | 1.5% | +7.21% | -23.29% | -1.34% | -25.64% | 611 |
