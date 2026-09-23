import Link from "next/link";

export default function Footer() {
  return (
    <footer className="py-6 px-6 border-t border-slate-800">
      <div className="max-w-3xl mx-auto flex justify-center gap-6">
        <Link href="/disclaimer" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
          利用上の注意・免責事項
        </Link>
        <Link href="/privacy" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
          プライバシーポリシー
        </Link>
        <a href="https://github.com/openisec/openisec-hpcr-drtl-demo/blob/main/LICENSE" target="_blank" rel="noopener noreferrer" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
          ライセンス
        </a>
      </div>
    </footer>
  );
}