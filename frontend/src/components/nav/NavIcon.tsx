import {
  BadgeCheck,
  Building2,
  Clock,
  CreditCard,
  FileText,
  PieChart,
  Settings,
  ShieldAlert,
  Users,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";

export type NavSectionKey =
  | "payments"
  | "approvals"
  | "history"
  | "attack"
  | "metrics"
  | "suppliers"
  | "company"
  | "audit"
  | "settings";

type DuotoneMode = "shapes" | "first-path" | "last-path" | "shapes-and-first";

interface NavIconSpec {
  icon: LucideIcon;
  toneClass: string;
  duotone: DuotoneMode;
}

const NAV_ICON_SPECS: Record<NavSectionKey, NavIconSpec> = {
  payments: {
    icon: CreditCard,
    toneClass: "hdr-tone-payments",
    duotone: "shapes",
  },
  approvals: {
    icon: BadgeCheck,
    toneClass: "hdr-tone-approvals",
    duotone: "first-path",
  },
  history: {
    icon: Clock,
    toneClass: "hdr-tone-history",
    duotone: "shapes",
  },
  attack: {
    icon: ShieldAlert,
    toneClass: "hdr-tone-attack",
    duotone: "first-path",
  },
  metrics: {
    icon: PieChart,
    toneClass: "hdr-tone-metrics",
    duotone: "first-path",
  },
  suppliers: {
    icon: Building2,
    toneClass: "hdr-tone-suppliers",
    duotone: "last-path",
  },
  company: {
    icon: Users,
    toneClass: "hdr-tone-company",
    duotone: "shapes-and-first",
  },
  audit: {
    icon: FileText,
    toneClass: "hdr-tone-history",
    duotone: "first-path",
  },
  settings: {
    icon: Settings,
    toneClass: "hdr-tone-settings",
    duotone: "first-path",
  },
};

export interface NavIconProps {
  section: NavSectionKey;
  active?: boolean;
  className?: string;
}

export function NavIcon({ section, active = false, className }: NavIconProps) {
  const { icon: Icon, toneClass, duotone } = NAV_ICON_SPECS[section];

  return (
    <span
      aria-hidden="true"
      data-active={active ? "true" : undefined}
      data-duotone={duotone}
      className={cn("hdr-tile", toneClass, className)}
    >
      <Icon className="size-5" strokeWidth={1.85} />
    </span>
  );
}
