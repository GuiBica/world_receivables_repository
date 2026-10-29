"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ROLE_LABEL, clearSession, type User } from "@/lib/api";

export default function Shell({ user, children }: { user: User; children: React.ReactNode }) {
  const router = useRouter();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand">
            Receivables Registry<span>Verification workbench</span>
          </Link>
          <div className="who">
            <span>
              {user.name} ({ROLE_LABEL[user.role]})
            </span>
            <button
              onClick={() => {
                clearSession();
                router.push("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="wrap">{children}</main>
    </>
  );
}
