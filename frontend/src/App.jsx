import { useEffect, useState } from "react";
import AuthPage from "./pages/AuthPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import { fetchMe } from "./lib/api";
import { clearToken, getToken, onTokenChange } from "./lib/auth";

export default function App() {
  const [token, setTokenState] = useState(getToken());
  const [user, setUser] = useState(null);

  useEffect(() => onTokenChange(setTokenState), []);

  // Validate a stored token (it may have expired) and load the account.
  useEffect(() => {
    if (!token) return;
    let active = true;
    fetchMe()
      .then((me) => active && setUser(me))
      .catch(() => active && clearToken()); // 401 -> back to the sign-in screen
    return () => {
      active = false;
    };
  }, [token]);

  if (!token) return <AuthPage />;
  if (!user) return <div className="auth-shell"><p className="sidebar__hint">Loading your account...</p></div>;
  // key: a different account gets a completely fresh chat state.
  return <ChatPage key={user.id} user={user} onLogout={() => { clearToken(); setUser(null); }} />;
}
