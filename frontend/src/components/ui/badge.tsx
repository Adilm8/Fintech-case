import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-[4px] border border-transparent px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/20 has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-[var(--brand-hover)]",
        secondary:
          "border-border bg-muted text-[var(--text-secondary)] [a]:hover:bg-muted/80",
        destructive:
          "border-[#E5A3A3] bg-card text-[#B91C1C] focus-visible:ring-destructive/20 [a]:hover:bg-[#FEF2F2]",
        outline:
          "border-border bg-muted/50 text-[var(--text-secondary)] [a]:hover:bg-muted [a]:hover:text-foreground",
        ghost:
          "text-[var(--text-secondary)] hover:bg-muted hover:text-foreground",
        link: "text-[var(--brand-text)] underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
