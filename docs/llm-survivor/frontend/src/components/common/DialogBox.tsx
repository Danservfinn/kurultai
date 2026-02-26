"use client";

import { useState, useEffect } from 'react';

interface DialogBoxProps {
  text: string;
}

export function DialogBox({ text }: DialogBoxProps) {
  const [displayedText, setDisplayedText] = useState('');
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    // Reset when text changes
    setDisplayedText('');
    setIsComplete(false);
    
    let currentIndex = 0;
    
    const intervalId = setInterval(() => {
      if (currentIndex < text.length) {
        setDisplayedText(text.slice(0, currentIndex + 1));
        currentIndex++;
      } else {
        setIsComplete(true);
        clearInterval(intervalId);
      }
    }, 20);

    return () => clearInterval(intervalId);
  }, [text]);

  return (
    <div className="gbc-box p-4 min-h-[100px] relative bg-white">
      <p className="text-[10px] leading-relaxed text-gbc-black">
        {displayedText}
        {isComplete && (
          <span className="inline-block ml-1 animate-bounce">▼</span>
        )}
      </p>
    </div>
  );
}
