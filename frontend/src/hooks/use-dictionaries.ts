"use client";

/**
 * React hooks that wrap the faculty / group dictionary API.
 *
 * Two flavours:
 *  - "public" hooks (no token) used during registration before the user
 *    can log in.
 *  - authenticated hooks reused inside the admin UI and the document
 *    upload form.
 *
 * The hooks intentionally cache nothing across mounts — the dataset is
 * tiny (tens of faculties, hundreds of groups) and each form needs the
 * latest list to honour edits an admin made seconds ago.
 */

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { dictionariesApi } from "@/lib/api";
import type {
  FacultyCreateData,
  FacultyResponse,
  GroupCreateData,
  GroupResponse,
  GroupUpdateData,
  StudyLevel,
} from "@/types/api";

interface DictionaryState<T> {
  items: T[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Public (registration form)
// ---------------------------------------------------------------------------

export function usePublicFaculties(): DictionaryState<FacultyResponse> {
  const [items, setItems] = useState<FacultyResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await dictionariesApi.listFacultiesPublic();
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load faculties");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { items, isLoading, error, refetch };
}

export function usePublicGroups(
  facultyId: string | null,
  level: StudyLevel | null,
): DictionaryState<GroupResponse> {
  const [items, setItems] = useState<GroupResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!facultyId) {
      setItems([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data = await dictionariesApi.listGroupsPublic(
        facultyId,
        level ?? undefined,
      );
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load groups");
    } finally {
      setIsLoading(false);
    }
  }, [facultyId, level]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { items, isLoading, error, refetch };
}

// ---------------------------------------------------------------------------
// Authenticated (admin pages, upload form)
// ---------------------------------------------------------------------------

export function useFaculties(): DictionaryState<FacultyResponse> {
  const { data: session } = useSession();
  const token = session?.accessToken;

  const [items, setItems] = useState<FacultyResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await dictionariesApi.listFaculties(token);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load faculties");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { items, isLoading, error, refetch };
}

export function useGroups(
  facultyId: string | null,
  level: StudyLevel | null = null,
): DictionaryState<GroupResponse> {
  const { data: session } = useSession();
  const token = session?.accessToken;

  const [items, setItems] = useState<GroupResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!token) return;
    if (!facultyId) {
      setItems([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data = await dictionariesApi.listGroups(
        token,
        facultyId,
        level ?? undefined,
      );
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load groups");
    } finally {
      setIsLoading(false);
    }
  }, [token, facultyId, level]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { items, isLoading, error, refetch };
}

// ---------------------------------------------------------------------------
// Mutations — used by the admin dictionaries page.
// ---------------------------------------------------------------------------

export function useDictionaryMutations() {
  const { data: session } = useSession();
  const token = session?.accessToken;

  return {
    createFaculty: async (data: FacultyCreateData) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.createFaculty(data, token);
    },
    updateFaculty: async (id: string, data: FacultyCreateData) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.updateFaculty(id, data, token);
    },
    deleteFaculty: async (id: string) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.deleteFaculty(id, token);
    },
    createGroup: async (data: GroupCreateData) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.createGroup(data, token);
    },
    updateGroup: async (id: string, data: GroupUpdateData) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.updateGroup(id, data, token);
    },
    deleteGroup: async (id: string) => {
      if (!token) throw new Error("Not authenticated");
      return dictionariesApi.deleteGroup(id, token);
    },
  };
}
