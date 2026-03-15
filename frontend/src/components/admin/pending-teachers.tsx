"use client";

import { Check, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { UserResponse } from "@/types/api";

interface PendingTeachersProps {
  teachers: UserResponse[];
  onApprove: (userId: string) => Promise<void>;
  onReject: (userId: string) => Promise<void>;
  isLoading: boolean;
}

export function PendingTeachers({
  teachers,
  onApprove,
  onReject,
  isLoading,
}: PendingTeachersProps) {
  const t = useTranslations("admin.pending");

  if (!isLoading && teachers.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {t("title")}
          {teachers.length > 0 && (
            <Badge variant="secondary">{teachers.length}</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {teachers.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t("empty")}
          </p>
        ) : (
          <div className="space-y-3">
            {teachers.map((teacher) => (
              <div
                key={teacher.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="space-y-1">
                  <p className="text-sm font-medium">{teacher.full_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {teacher.email}
                  </p>
                  <div className="flex gap-2 text-xs text-muted-foreground">
                    {teacher.faculty && <span>{teacher.faculty}</span>}
                    {teacher.department && <span>· {teacher.department}</span>}
                    {teacher.position && <span>· {teacher.position}</span>}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onApprove(teacher.id)}
                    className="text-green-600 hover:text-green-700 hover:bg-green-50"
                  >
                    <Check className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onReject(teacher.id)}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
