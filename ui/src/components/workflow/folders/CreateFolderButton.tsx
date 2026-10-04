'use client';

import { FolderPlus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

import { createFolderApiV1FolderPost } from '@/client/sdk.gen';
import { Button } from '@/components/ui/button';
import { useCopy } from "@/i18n/LocaleProvider";

import { FolderFormDialog } from './FolderFormDialog';


export function CreateFolderButton() {
    const copy = useCopy();
    const router = useRouter();
    const [isOpen, setIsOpen] = useState(false);

    const handleCreate = async (name: string) => {
        const response = await createFolderApiV1FolderPost({ body: { name } });
        if (response.error) {
            // 409 = duplicate name; surface the server's message when present.
            const detail =
                (response.error as { detail?: string })?.detail ??
                copy("Failed to create folder");
            toast.error(detail);
            throw new Error(detail);
        }
        toast.success(copy("Folder \"{value0}\" created", {value0: name}));
        router.refresh();
    };

    return (
        <>
            <Button variant="outline" onClick={() => setIsOpen(true)}>
                <FolderPlus className="w-4 h-4 mr-2" />{copy("New Folder")}</Button>
            <FolderFormDialog
                open={isOpen}
                onOpenChange={setIsOpen}
                title={copy("Create folder")}
                submitLabel="Create"
                onSubmit={handleCreate}
            />
        </>
    );
}
