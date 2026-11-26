import { toast } from "sonner";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface NotifyOptions {
  description?: string;
  action?: ToastAction;
  duration?: number;
}

export const notify = {
  success(title: string, options?: string | NotifyOptions) {
    const resolved =
      typeof options === "string" ? { description: options } : options;
    return toast.success(title, resolved);
  },
  error(title: string, options?: string | NotifyOptions) {
    const resolved =
      typeof options === "string" ? { description: options } : options;
    return toast.error(title, resolved);
  },
  warning(title: string, options?: string | NotifyOptions) {
    const resolved =
      typeof options === "string" ? { description: options } : options;
    return toast.warning(title, resolved);
  },
  info(title: string, options?: string | NotifyOptions) {
    const resolved =
      typeof options === "string" ? { description: options } : options;
    return toast.info(title, resolved);
  },
};

export { toast };
