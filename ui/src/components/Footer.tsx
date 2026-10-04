"use client";


import { useCopy } from "@/i18n/LocaleProvider";
export default function Footer() {
    const copy = useCopy();
  return (
    <footer className="fixed bottom-0 left-0 right-0 bg-background border-t border-border py-4 px-6">
      <div className="flex justify-center items-center gap-6 text-sm text-muted-foreground">
        <a
          href="https://www.dograh.com/privacy-policy"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-foreground transition-colors"
        >{copy("Privacy Policy")}</a>
        <span className="text-border">|</span>
        <a
          href="https://www.dograh.com/terms-of-service"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-foreground transition-colors"
        >{copy("Terms of Service")}</a>
      </div>
    </footer>
  );
}
