"use client";

import { useEffect, useRef, type Ref } from "react";
import Link from "next/link";
import { cn } from "cn";
import { NavIcon, type NavSectionKey } from "./NavIcon";

export interface NavTileItem {
  key: NavSectionKey;
  href: string;
  label: string;
  active: boolean;
  badge: number | null;
  onClick?: () => void;
}

interface NavTileProps {
  item: NavTileItem;
  ref?: Ref<HTMLAnchorElement>;
}

export function NavTile({ item, ref }: NavTileProps) {
  return (
    <Link
      ref={ref}
      href={item.href}
      onClick={item.onClick}
      aria-current={item.active ? "page" : undefined}
      data-active={item.active ? "true" : undefined}
      className="hdr-nav-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <NavIcon section={item.key} active={item.active} />
      <span className="leading-tight">{item.label}</span>
      {item.badge !== null && (
        <span
          data-active={item.active ? "true" : undefined}
          data-positive={item.badge > 0 ? "true" : undefined}
          className="hdr-nav-badge tabular-nums"
        >
          {item.badge}
        </span>
      )}
    </Link>
  );
}

export interface NavTileListProps {
  items: readonly NavTileItem[];
  ariaLabel: string;
  scrollKey: string;
  className?: string;
}

export function NavTileList({
  items,
  ariaLabel,
  scrollKey,
  className,
}: NavTileListProps) {
  const activeTabRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    const el = activeTabRef.current;
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  }, [scrollKey]);

  return (
    <nav aria-label={ariaLabel} className={cn("min-w-0", className)}>
      <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto py-1 -my-1 md:gap-2">
        {items.map((item) => (
          <NavTile
            key={item.href}
            item={item}
            ref={item.active ? activeTabRef : undefined}
          />
        ))}
      </div>
    </nav>
  );
}
