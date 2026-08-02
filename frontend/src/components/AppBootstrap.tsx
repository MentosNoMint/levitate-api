"use client";

import React, { useEffect } from "react";
import { useDashboardStore } from "@/store/dashboardStore";

interface AppBootstrapProps {
  children: React.ReactNode;
}

export default function AppBootstrap({ children }: AppBootstrapProps) {
  const token = useDashboardStore((state) => state.token);
  const user = useDashboardStore((state) => state.user);
  const setToken = useDashboardStore((state) => state.setToken);
  const fetchConfig = useDashboardStore((state) => state.fetchConfig);
  const fetchUser = useDashboardStore((state) => state.fetchUser);
  const fetchData = useDashboardStore((state) => state.fetchData);
  const setTheme = useDashboardStore((state) => state.setTheme);
  const setLanguage = useDashboardStore((state) => state.setLanguage);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const storedTheme = localStorage.getItem("theme");
      if (storedTheme === "light" || storedTheme === "dark") {
        setTheme(storedTheme);
      } else {
        setTheme("dark");
      }

      const storedLang = localStorage.getItem("language");
      if (storedLang === "en" || storedLang === "ru") {
        setLanguage(storedLang);
      }
    }
  }, [setTheme, setLanguage]);

  useEffect(() => {
    const initializeAuth = async () => {
      let currentToken = null;
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const tokenFromUrl = params.get("auth_token");
        const googleConnect = params.get("google_connect");
        
        if (googleConnect === "success") {
          window.history.replaceState(null, "", window.location.pathname);
        }
        
        const getCookie = (name: string) => {
          const value = `; ${document.cookie}`;
          const parts = value.split(`; ${name}=`);
          if (parts.length === 2) return parts.pop()?.split(";").shift();
          return undefined;
        };

        const cookieToken = getCookie("auth_token");
        const decodedToken = cookieToken ? decodeURIComponent(cookieToken) : undefined;

        if (tokenFromUrl) {
          currentToken = tokenFromUrl;
          setToken(tokenFromUrl);
          window.history.replaceState(null, "", window.location.pathname);
        } else if (decodedToken) {
          currentToken = decodedToken;
          setToken(decodedToken);
          localStorage.setItem("auth_token", decodedToken);
        } else {
          currentToken = localStorage.getItem("auth_token");
          if (currentToken) {
            setToken(currentToken);
            document.cookie = `auth_token=${currentToken}; path=/; max-age=2592000; SameSite=Lax`;
          }
        }
      }

      await fetchConfig();
      if (currentToken) {
        await fetchUser();
      } else {
        useDashboardStore.setState({ isAuthLoading: false });
      }
    };

    initializeAuth();
    // Run once on mount: zustand actions are stable, and re-running on every
    // route/token change duplicated /auth/config and /auth/me requests (#27)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setToken, fetchConfig, fetchUser]);

  useEffect(() => {
    if (user && token) {
      fetchData();
      const interval = setInterval(() => {
        fetchData();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [user, token, fetchData]);

  return <>{children}</>;
}
