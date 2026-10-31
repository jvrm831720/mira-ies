import * as React from "react";
import { Dialog, DialogContent } from "./dialog";
import { cn } from "@/lib/utils";

export function Drawer({ open, onOpenChange, children, side = "right", className }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  side?: "left" | "right";
  className?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} className={cn(
      "m-0 ml-auto h-dvh max-h-dvh w-[min(100%,28rem)] max-w-none rounded-none border-y-0 shadow-[var(--shadow-overlay)]",
      side === "left" && "mr-auto ml-0",
      className
    )}>
      <DialogContent className="min-h-full p-6">{children}</DialogContent>
    </Dialog>
  );
}
