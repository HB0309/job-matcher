"use client";

import { useState, useEffect, ReactNode } from "react";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const [checked, setChecked] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoggedIn(auth.isLoggedIn());
    setChecked(true);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const fn = mode === "login" ? api.login : api.register;
      const { access_token } = await fn(email, password);
      auth.setToken(access_token);
      setLoggedIn(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    auth.clearToken();
    setLoggedIn(false);
    setEmail("");
    setPassword("");
  }

  if (!checked) return null;
  if (loggedIn) return <>{children}</>;

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white border border-gray-200 rounded-lg p-8 w-full max-w-sm space-y-5 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Job Matcher</h1>
          <p className="text-sm text-gray-500 mt-1">
            {mode === "login" ? "Sign in to your account" : "Create an account"}
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "…" : mode === "login" ? "Sign in" : "Register"}
          </button>
        </form>

        <p className="text-xs text-center text-gray-500">
          {mode === "login" ? "Don't have an account? " : "Already have an account? "}
          <button
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
            className="text-blue-600 hover:underline"
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
