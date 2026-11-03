"use client";

import { Suspense } from "react";
import { StudentsListPage } from "@/components/students/students-list-page";
import { Skeleton } from "@/components/ui/skeleton";

export default function AlunosPage() {
  return (
    <Suspense
      fallback={
        <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 py-10">
          <Skeleton className="h-8 w-48" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
          <Skeleton className="h-64 rounded-xl" />
        </main>
      }
    >
      <StudentsListPage />
    </Suspense>
  );
}
