# 📡 API Documentation

## Chat

### POST /chat

Generate AI response.

### POST /chat/stream

Streaming AI response.

---

## Chats

GET /chats

Returns all chats.

POST /chats

Create new chat.

PUT /chats/{id}

Rename chat.

DELETE /chats/{id}

Delete chat.

---

## Documents

POST /documents/upload

Upload PDF.

GET /documents

List uploaded PDFs.

DELETE /documents/{filename}

Delete PDF.