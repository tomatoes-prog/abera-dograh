"use client";

// Anti-spam quick-check shown as a popup ON TOP of a lead form (via the
// LeadModalShell `overlay` slot) so it can't be scrolled past or missed.
// Generates a fresh sum each time it mounts; calls onVerified once the correct
// answer is confirmed, onCancel to dismiss back to the form.

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCopy } from "@/i18n/LocaleProvider";


export function CaptchaChallenge({
  onVerified,
  onCancel,
}: {
  onVerified: () => void;
  onCancel: () => void;
}) {
    const copy = useCopy();
  const [a, setA] = useState(0);
  const [b, setB] = useState(0);
  const [answer, setAnswer] = useState("");

  // Fresh challenge whenever this mounts (the parent mounts it on demand).
  // Math.random is allowed in the browser runtime (not a workflow script).
  const regenerate = () => {
    setA(Math.floor(Math.random() * 8) + 1);
    setB(Math.floor(Math.random() * 8) + 1);
    setAnswer("");
  };
  useEffect(() => {
    regenerate();
  }, []);

  const confirm = () => {
    if (answer.trim() !== "" && parseInt(answer, 10) === a + b) {
      onVerified();
    } else {
      toast.error(copy("That's not quite right - try again."));
      regenerate();
    }
  };

  return (
    <div className="lead-form-slab relative w-full max-w-xs overflow-hidden rounded-xl border border-border/70 bg-card shadow-2xl">
      <div className="lead-form-underline relative space-y-4 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-cta/25 bg-cta/10 text-cta">
            <ShieldCheck className="size-4" />
          </span>
          <div className="space-y-1">
            <p className="text-sm font-semibold">{copy("Quick check")}</p>
            <p className="text-xs text-muted-foreground">{copy("Confirm you're human before we send this.")}</p>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="captcha-answer">{copy("What is ")}{a} + {b}?
          </Label>
          <Input
            id="captcha-answer"
            inputMode="numeric"
            autoFocus
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") confirm();
            }}
            placeholder={copy("Answer")}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>{copy("Cancel")}</Button>
          <Button
            type="button"
            onClick={confirm}
            className="bg-cta text-cta-foreground shadow-md shadow-cta/25 hover:bg-cta/90 hover:shadow-cta/35 focus-visible:ring-cta/50"
          >{copy("Confirm & submit")}</Button>
        </div>
      </div>
    </div>
  );
}
