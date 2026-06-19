# SEPA Stock API cho Custom GPT

Đây là backend proxy để Custom GPT Actions gọi dữ liệu chứng khoán.

## Vì sao cần backend này?

Custom GPT không tự lấy dữ liệu realtime từ màn hình web hay TradingView. GPT chỉ gọi được các endpoint HTTPS được khai báo trong `openapi.yaml`.

Luồng đúng:

```text
Custom GPT -> SEPA Stock API -> Market data provider -> JSON -> Custom GPT
```

## Chạy local để test

```bash
npm install
npm run dev
```

Mở:

```text
http://localhost:3000/health
http://localhost:3000/price/FPT?api_key=change-this-secret
http://localhost:3000/sepa-score/FPT?api_key=change-this-secret
```

Localhost chỉ dùng để test trên máy. GPT Actions cần domain public HTTPS.

## Deploy nhanh

Deploy folder này lên Render, Railway, Fly.io, VPS, hoặc dịch vụ Node.js bất kỳ.

Biến môi trường cần đặt:

```text
PORT=3000
ACTION_API_KEY=mot-key-bi-mat-cua-em
DATA_PROVIDER=demo
```

Sau khi deploy xong, em sẽ có URL kiểu:

```text
https://sepa-stock-api.onrender.com
```

## Gắn vào Custom GPT Actions

1. Mở `openapi.yaml`.
2. Thay:

```yaml
servers:
  - url: https://YOUR-DEPLOYED-DOMAIN.com
```

bằng domain deploy thật, ví dụ:

```yaml
servers:
  - url: https://sepa-stock-api.onrender.com
```

3. Dán toàn bộ `openapi.yaml` vào phần Schema của GPT Actions.
4. Trong Authentication, chọn `API Key`.
5. Chọn kiểu `Bearer`.
6. Dán đúng giá trị `ACTION_API_KEY`.
7. Bấm `Kiểm tra` từng action.

## Nối dữ liệu thật

Bản này đang dùng `DATA_PROVIDER=demo` để test GPT Actions chạy trước.

Khi em có API dữ liệu thật, đổi:

```text
DATA_PROVIDER=custom
MARKET_DATA_BASE_URL=https://api-data-that-cua-em.com
MARKET_DATA_API_KEY=key-cua-provider
```

Backend sẽ gọi các endpoint sau từ provider:

```text
GET /price/{symbol}
GET /history/{symbol}
GET /fundamental/{symbol}
GET /financial-indicators/{symbol}
GET /market-cap/{symbol}
```

Nếu provider của em có format khác, sửa hàm `fetchCustomProvider()` hoặc thêm adapter riêng trong `server.js`.

## Lưu ý quan trọng

- Dữ liệu demo không dùng để ra quyết định đầu tư.
- Muốn realtime thật cho chứng khoán Việt Nam thường cần API/provider có license.
- Response nên trả JSON thô, không trả đoạn văn dài. GPT sẽ tự phân tích từ JSON đó.
- API deploy phải dùng HTTPS public, không dùng `localhost`.
