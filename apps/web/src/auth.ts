import NextAuth from "next-auth";
import Apple from "next-auth/providers/apple";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import {
  authenticateUser,
  createUser,
  findUserByEmail,
  upsertSocialUser,
} from "@/lib/local-users";

const googleConfigured = Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
const appleConfigured = Boolean(process.env.AUTH_APPLE_ID && process.env.AUTH_APPLE_SECRET);
/** When OAuth secrets are missing, Google/Apple buttons still create a real local session. */
const demoOauth = process.env.AUTH_DEMO_OAUTH !== "false";

const providers = [
  ...(googleConfigured
    ? [
        Google({
          clientId: process.env.AUTH_GOOGLE_ID!,
          clientSecret: process.env.AUTH_GOOGLE_SECRET!,
        }),
      ]
    : []),
  ...(appleConfigured
    ? [
        Apple({
          clientId: process.env.AUTH_APPLE_ID!,
          clientSecret: process.env.AUTH_APPLE_SECRET!,
        }),
      ]
    : []),
  Credentials({
    id: "credentials",
    name: "Email",
    credentials: {
      email: { label: "Email", type: "email" },
      password: { label: "Password", type: "password" },
      name: { label: "Name", type: "text" },
      mode: { label: "Mode", type: "text" },
    },
    async authorize(credentials) {
      const email = String(credentials?.email || "").trim().toLowerCase();
      const password = String(credentials?.password || "");
      const mode = String(credentials?.mode || "signin");
      const name = String(credentials?.name || "");
      if (!email || !password) return null;

      if (mode === "signup") {
        const user = createUser({ email, password, name });
        return { id: user.id, email: user.email, name: user.name };
      }

      const user = authenticateUser(email, password);
      if (!user) return null;
      return { id: user.id, email: user.email, name: user.name };
    },
  }),
  // Demo Google / Apple when real OAuth apps are not configured yet
  ...(demoOauth && !googleConfigured
    ? [
        Credentials({
          id: "google-demo",
          name: "Google",
          credentials: {
            email: { label: "Email", type: "email" },
            name: { label: "Name", type: "text" },
          },
          async authorize(credentials) {
            const email = String(credentials?.email || "investor@gmail.com").trim().toLowerCase();
            const name = String(credentials?.name || "Google Investor");
            const user = upsertSocialUser({ email, name, provider: "google" });
            return { id: user.id, email: user.email, name: user.name };
          },
        }),
      ]
    : []),
  ...(demoOauth && !appleConfigured
    ? [
        Credentials({
          id: "apple-demo",
          name: "Apple",
          credentials: {
            email: { label: "Email", type: "email" },
            name: { label: "Name", type: "text" },
          },
          async authorize(credentials) {
            const email = String(credentials?.email || "investor@icloud.com").trim().toLowerCase();
            const name = String(credentials?.name || "Apple Investor");
            const user = upsertSocialUser({ email, name, provider: "apple" });
            return { id: user.id, email: user.email, name: user.name };
          },
        }),
      ]
    : []),
];

export const { handlers, auth, signIn, signOut } = NextAuth({
  secret: process.env.AUTH_SECRET || "landsignal-dev-auth-secret-change-me",
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  providers,
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google" || account?.provider === "apple") {
        const email = user.email || `${account.provider}-${account.providerAccountId}@users.landsignal.local`;
        const name = user.name || (account.provider === "google" ? "Google user" : "Apple user");
        const saved = upsertSocialUser({
          email,
          name,
          provider: account.provider,
          subject: account.providerAccountId,
        });
        user.id = saved.id;
        user.email = saved.email;
        user.name = saved.name;
      }
      return true;
    },
    async jwt({ token, user }) {
      if (user) {
        token.sub = user.id || token.sub;
        token.email = user.email;
        token.name = user.name;
      }
      if (token.email && !token.sub) {
        const existing = findUserByEmail(String(token.email));
        if (existing) token.sub = existing.id;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = String(token.sub || "");
        session.user.email = String(token.email || session.user.email || "");
        session.user.name = String(token.name || session.user.name || "");
      }
      return session;
    },
  },
  trustHost: true,
});

export const authProviders = {
  google: googleConfigured ? ("google" as const) : ("google-demo" as const),
  apple: appleConfigured ? ("apple" as const) : ("apple-demo" as const),
  googleLive: googleConfigured,
  appleLive: appleConfigured,
};
