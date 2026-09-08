import assert from "node:assert/strict";
import { displayNameFromUser } from "../app/lib/userDisplay.ts";

assert.equal(displayNameFromUser(null), "");
assert.equal(
  displayNameFromUser({
    email: "ada@example.com",
    user_metadata: { full_name: "Ada Lovelace" },
  }),
  "Ada Lovelace",
);
assert.equal(
  displayNameFromUser({
    email: "ada@example.com",
    user_metadata: { name: "Ada" },
  }),
  "Ada",
);
assert.equal(
  displayNameFromUser({ email: "ada@example.com", user_metadata: {} }),
  "ada",
);
assert.equal(displayNameFromUser({ email: "solo", user_metadata: null }), "solo");

console.log("userDisplay tests passed");
