import { createHash, randomBytes, scryptSync, timingSafeEqual } from "crypto";
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

function newId(seed: string) {
  return createHash("sha256").update(seed).digest("hex").slice(0, 24);
}

export function findUserByEmail(email: string) {
  const normalized = email.trim().toLowerCase();
  return readStore().users.find((u) => u.email === normalized) || null;
}

export function createUser(input: {
  email: string;
  name: string;
  password: string;
}) {
  const email = input.email.trim().toLowerCase();
  if (!email || !email.includes("@")) throw new Error("Enter a valid email.");
  if (input.password.length < 8) throw new Error("Password must be at least 8 characters.");
  const store = readStore();
  if (store.users.some((u) => u.email === email)) {
    throw new Error("An account with this email already exists. Sign in instead.");
  }
  const user: LocalUser = {
    id: newId(`credentials:${email}:${Date.now()}`),
    email,
    name: input.name.trim() || email.split("@")[0],
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
  const store = readStore();
  const existing = store.users.find((u) => u.email === email);
  if (existing) {
    existing.name = input.name.trim() || existing.name;
    existing.provider = input.provider;
    writeStore(store);
    return existing;
  }
  const user: LocalUser = {
    id: newId(`${input.provider}:${input.subject || email}`),
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
