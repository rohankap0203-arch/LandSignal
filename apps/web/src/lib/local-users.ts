import { createHash, randomBytes, randomUUID, scryptSync, timingSafeEqual } from "crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import path from "path";

export type LocalUser = {
  id: string;
  email: string;
  name: string;
  passwordHash: string;
  provider: "credentials" | "google" | "apple";
  createdAt: string;
};

type StoreFile = { users: LocalUser[] };

const DATA_DIR = path.join(process.cwd(), ".data");
const STORE_PATH = path.join(DATA_DIR, "accounts.json");
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Stable namespace so social remounts keep the same UUID without a DB. */
const LANDSIGNAL_NS = "a3f1c8e2-5b94-4d6f-9c21-7e8a0b1d2f34";

function readStore(): StoreFile {
  try {
    if (!existsSync(STORE_PATH)) return { users: [] };
    const raw = readFileSync(STORE_PATH, "utf8");
    const parsed = JSON.parse(raw) as StoreFile;
    return { users: Array.isArray(parsed.users) ? parsed.users : [] };
  } catch {
    return { users: [] };
  }
}

function writeStore(store: StoreFile) {
  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
  writeFileSync(STORE_PATH, JSON.stringify(store, null, 2), "utf8");
}

function hashPassword(password: string, salt?: string) {
  const s = salt || randomBytes(16).toString("hex");
  const hash = scryptSync(password, s, 32).toString("hex");
  return `${s}:${hash}`;
}

function verifyPassword(password: string, packed: string) {
  const [salt, hash] = packed.split(":");
  if (!salt || !hash) return false;
  const next = scryptSync(password, salt, 32);
  const prev = Buffer.from(hash, "hex");
  if (prev.length !== next.length) return false;
  return timingSafeEqual(prev, next);
}

/** UUID v5 (SHA-1) — compatible with FastAPI `UUID` fields. */
export function uuidFromSeed(seed: string): string {
  const ns = LANDSIGNAL_NS.replace(/-/g, "");
  const nsBytes = Buffer.from(ns, "hex");
  const hash = createHash("sha1").update(nsBytes).update(seed).digest();
  hash[6] = (hash[6]! & 0x0f) | 0x50;
  hash[8] = (hash[8]! & 0x3f) | 0x80;
  const hex = hash.subarray(0, 16).toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function isUuid(value: string) {
  return UUID_RE.test(value);
}

function ensureUuidId(user: LocalUser): LocalUser {
  if (isUuid(user.id)) return user;
  const seed =
    user.provider === "credentials"
      ? `credentials:${user.email}`
      : `${user.provider}:${user.email}`;
  user.id = uuidFromSeed(seed);
  return user;
}

function normalizeStore(store: StoreFile): StoreFile {
  let dirty = false;
  for (const user of store.users) {
    const before = user.id;
    ensureUuidId(user);
    if (user.id !== before) dirty = true;
  }
  if (dirty) writeStore(store);
  return store;
}

export function findUserByEmail(email: string) {
  const normalized = email.trim().toLowerCase();
  const store = normalizeStore(readStore());
  return store.users.find((u) => u.email === normalized) || null;
}

export function findUserById(id: string) {
  const store = normalizeStore(readStore());
  return store.users.find((u) => u.id === id) || null;
}

export function createUser(input: {
  email: string;
  name: string;
  password: string;
}) {
  const email = input.email.trim().toLowerCase();
  const name = input.name.trim();
  if (!email || !email.includes("@")) throw new Error("Enter a valid email.");
  if (!name) throw new Error("Enter your name.");
  if (input.password.length < 8) throw new Error("Password must be at least 8 characters.");
  const store = normalizeStore(readStore());
  if (store.users.some((u) => u.email === email)) {
    throw new Error("An account with this email already exists. Sign in instead.");
  }
  const user: LocalUser = {
    id: randomUUID(),
    email,
    name: name || email.split("@")[0] || "LandSignal user",
    passwordHash: hashPassword(input.password),
    provider: "credentials",
    createdAt: new Date().toISOString(),
  };
  store.users.push(user);
  writeStore(store);
  return user;
}

export function authenticateUser(email: string, password: string) {
  const user = findUserByEmail(email);
  if (!user || user.provider !== "credentials") return null;
  if (!verifyPassword(password, user.passwordHash)) return null;
  return user;
}

/** Upsert a social-login profile into the local account book. */
export function upsertSocialUser(input: {
  email: string;
  name: string;
  provider: "google" | "apple";
  subject?: string;
}) {
  const email = input.email.trim().toLowerCase();
  const store = normalizeStore(readStore());
  const existing = store.users.find((u) => u.email === email);
  if (existing) {
    existing.name = input.name.trim() || existing.name;
    existing.provider = input.provider;
    writeStore(store);
    return existing;
  }
  const user: LocalUser = {
    id: uuidFromSeed(`${input.provider}:${input.subject || email}`),
    email,
    name: input.name.trim() || email.split("@")[0] || "LandSignal user",
    passwordHash: "",
    provider: input.provider,
    createdAt: new Date().toISOString(),
  };
  store.users.push(user);
  writeStore(store);
  return user;
}

export function listUsers() {
  return normalizeStore(readStore()).users.map(({ passwordHash: _pw, ...rest }) => rest);
}
