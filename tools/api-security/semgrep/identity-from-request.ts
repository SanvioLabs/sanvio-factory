import express from "express";

const app = express();

app.post("/v1/interpret", (req, res) => {
  // ruleid: api-security.identity-from-request.typescript
  const user = req.body.userId;
  // ruleid: api-security.identity-from-request.typescript
  const device = req.query["device_id"];
  // ruleid: api-security.identity-from-request.typescript
  const owner = req.headers["x-user-id"];
  // ok: api-security.identity-from-request.typescript
  const text = req.body.text;
  // ok: api-security.identity-from-request.typescript
  const target = req.params.userId;
  res.json({ user, device, owner, text, target });
});

export const handler = async (event: any) => {
  const body = JSON.parse(event.body);
  // ruleid: api-security.identity-from-request.typescript
  const user = body.user_id;
  // ok: api-security.identity-from-request.typescript
  const text = body.text;
  return { user, text };
};
