"""
Skill Watcher for Python - Monitors /data/skills/ for changes
Uses watchdog for cross-platform file watching
"""

import asyncio
import os
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(os.getenv('SKILLS_DIR', '/data/skills'))

class SkillReloadHandler(FileSystemEventHandler):
    """Handles file system events for skill changes"""

    def __init__(self, on_change=None):
        super().__init__()
        self.on_change = on_change
        self._reload_event = asyncio.Event()

    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            skill_name = Path(event.src_path).stem
            logger.info(f"[SkillWatcher] Skill modified: {skill_name}")
            if self.on_change:
                self.on_change('change', skill_name, event.src_path)
            # Check for reload signal
            if skill_name == '.reload':
                self._reload_event.set()

    def on_created(self, event):
        if event.src_path.endswith('.md'):
            skill_name = Path(event.src_path).stem
            logger.info(f"[SkillWatcher] Skill added: {skill_name}")
            if self.on_change:
                self.on_change('add', skill_name, event.src_path)

    def on_deleted(self, event):
        if event.src_path.endswith('.md'):
            skill_name = Path(event.src_path).stem
            logger.info(f"[SkillWatcher] Skill removed: {skill_name}")
            if self.on_change:
                self.on_change('remove', skill_name, event.src_path)

    def wait_for_reload(self, timeout=5):
        """Wait for a reload signal"""
        return asyncio.wait_for(self._reload_event.wait(), timeout)

async def start_skill_watcher(on_change=None):
    """Start the skill watcher in the background"""
    skills_dir = SKILLS_DIR

    # Ensure skills directory exists
    skills_dir.mkdir(parents=True, exist_ok=True)

    event_handler = SkillReloadHandler(on_change=on_change)
    observer = Observer()
    observer.schedule(event_handler, str(skills_dir), recursive=True)
    observer.start()
    logger.info(f"[SkillWatcher] Watching {skills_dir}")

    # List initial skills
    initial_skills = list(skills_dir.glob('*.md'))
    logger.info(f"[SkillWatcher] Initial skills: {[s.stem for s in initial_skills if s.stem != '.reload']}")

    return observer

# For standalone testing
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    async def main():
        observer = await start_skill_watcher()
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()

    asyncio.run(main())
