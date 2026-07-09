import { useState } from "react";
import { tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { ChatView } from "./components/ChatView";

export function App() {
  const [loggedIn, setLoggedIn] = useState(() => Boolean(tokenStore.get()));

  const handleLogout = () => {
    tokenStore.clear();
    setLoggedIn(false);
  };

  return loggedIn ? (
    <ChatView onLogout={handleLogout} />
  ) : (
    <LoginView onAuthed={() => setLoggedIn(true)} />
  );
}
