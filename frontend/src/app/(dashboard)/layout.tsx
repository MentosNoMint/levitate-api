"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useDashboardStore } from "@/store/dashboardStore";
import DashboardLayout from "@/components/DashboardLayout";

interface DashboardRouteLayoutProps {
  children: React.ReactNode;
}

export default function DashboardRouteLayout({ children }: DashboardRouteLayoutProps) {
  const { user, isAuthLoading } = useDashboardStore();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthLoading && !user) {
      router.replace("/login");
    }
  }, [user, isAuthLoading, router]);

  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-[var(--bg-app)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
          <span className="text-xs text-[var(--text-muted)] font-medium tracking-wider uppercase">
            Loading...
          </span>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return <DashboardLayout>{children}</DashboardLayout>;
}
