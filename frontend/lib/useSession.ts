"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, clearSession, getUser, type User } from "./api";

/** Returns the signed-in user (or sends the visitor to /login). */
export function useSession() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const u = getUser();
    if (!u) router.replace("/login");
    setUser(u);
    setReady(true);
  }, [router]);

  /** Turn an error into a message; an expired session goes back to /login. */
  const explain = useCallback(
    (e: unknown): string => {
      if (e instanceof ApiError && e.status === 401) {
        clearSession();
        router.replace("/login");
        return "Your session has expired. Please sign in again.";
      }
      return e instanceof Error ? e.message : "Something went wrong";
    },
    [router],
  );

  return { user, ready, explain };
}
