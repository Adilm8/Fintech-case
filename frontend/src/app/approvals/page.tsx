"use client";

import { useEffect } from "react";
import { useAppData } from "@/components/AppShell";
import { DirectorScreen } from "@/components/DirectorScreen";

export default function ApprovalsPage() {
  const {
    approvals,
    isLoading,
    resetCounter,
    analystMode,
    setAnalystMode,
    loadData,
    reportNetworkError,
  } = useAppData();

  useEffect(() => {
    return () => {
      setAnalystMode(false);
    };
  }, [setAnalystMode]);

  return (
    <DirectorScreen
      key={`director-${resetCounter}`}
      approvals={approvals}
      isLoading={isLoading}
      analystMode={analystMode}
      onAnalystModeChange={setAnalystMode}
      onRefresh={() => loadData(false)}
      onNetworkError={reportNetworkError}
    />
  );
}
