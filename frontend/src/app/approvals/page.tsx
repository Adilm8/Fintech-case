"use client";

import { useAppData } from "@/components/AppShell";
import { DirectorScreen } from "@/components/DirectorScreen";

export default function ApprovalsPage() {
  const { approvals, isLoading, resetCounter, loadData, reportNetworkError } =
    useAppData();

  return (
    <DirectorScreen
      key={`director-${resetCounter}`}
      approvals={approvals}
      isLoading={isLoading}
      onRefresh={() => loadData(false)}
      onNetworkError={reportNetworkError}
    />
  );
}
