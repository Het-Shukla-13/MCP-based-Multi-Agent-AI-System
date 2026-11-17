import { useState } from "react";
import { errorMessage, login, register } from "../lib/api";
import { setSession } from "../lib/auth";
import ThemeToggle from "../components/ThemeToggle";

export default function AuthPage() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (isRegister && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const session = isRegister ? await register(email, password) : await login(email, password);
      setSession(session); // App re-renders into the chat
    } catch (err) {
      setError(errorMessage(err, isRegister ? "Could not create the account." : "Could not sign in."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-shell__theme"><ThemeToggle /></div>
      <form className="auth-card" onSubmit={submit}>
        <p className="sidebar__eyebrow">Multi-Agent Assistant</p>
        <h1>{isRegister ? "Create your account" : "Sign in"}</h1>

        <label className="auth-field">
          <span>Email</span>
          <input autoComplete="email" onChange={(e) => setEmail(e.target.value)} required type="email" value={email} />
        </label>
        <label className="auth-field">
          <span>Password</span>
          <input
            autoComplete={isRegister ? "new-password" : "current-password"}
            minLength={isRegister ? 8 : undefined}
            onChange={(e) => setPassword(e.target.value)}
            required
            type="password"
            value={password}
          />
        </label>

        {error ? <p className="auth-error" role="alert">{error}</p> : null}

        <button className="primary-button" disabled={busy} type="submit">
          {busy ? "Please wait..." : isRegister ? "Create account" : "Sign in"}
        </button>
        <button className="link-button" onClick={() => { setMode(isRegister ? "login" : "register"); setError(""); }} type="button">
          {isRegister ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </form>
    </div>
  );
}
