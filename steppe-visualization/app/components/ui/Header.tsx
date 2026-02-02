'use client';

import { Map, Settings, HelpCircle, LayoutGrid } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

interface HeaderProps {
  onToggleMap?: () => void;
  onToggleSettings?: () => void;
  onToggleHelp?: () => void;
}

export function Header({ onToggleMap, onToggleSettings, onToggleHelp }: HeaderProps) {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 bg-gradient-to-b from-black/60 to-transparent">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-500 to-red-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
          <Map className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">
            Mongol Empire Command
          </h1>
          <p className="text-sm text-white/60">
            AI Agent Visualization • 6 Khans • Real-time Activity
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Link href="/mission-control">
          <Button
            variant="ghost"
            size="icon"
            className="text-white/70 hover:text-white hover:bg-white/10"
            title="Mission Control"
          >
            <LayoutGrid className="w-5 h-5" />
          </Button>
        </Link>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleMap}
          className="text-white/70 hover:text-white hover:bg-white/10"
        >
          <Map className="w-5 h-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSettings}
          className="text-white/70 hover:text-white hover:bg-white/10"
        >
          <Settings className="w-5 h-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleHelp}
          className="text-white/70 hover:text-white hover:bg-white/10"
        >
          <HelpCircle className="w-5 h-5" />
        </Button>
      </div>
    </header>
  );
}
