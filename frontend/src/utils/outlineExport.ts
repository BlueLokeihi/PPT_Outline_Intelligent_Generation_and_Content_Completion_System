import type { OutlineResult } from '@/types';

function sanitizeFileName(name: string): string {
  const safe = name.replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
  return safe.slice(0, 64) || 'outline';
}

export function buildOutlineMarkdown(outline: OutlineResult): string {
  const lines: string[] = [`# ${outline.title}`];

  if (outline.assumptions && outline.assumptions.length > 0) {
    lines.push('', '## 假设前提');
    outline.assumptions.forEach((item) => {
      lines.push(`- ${item}`);
    });
  }

  outline.chapters.forEach((chapter, chapterIndex) => {
    lines.push('', `## ${chapterIndex + 1}. ${chapter.title}`);

    chapter.pages.forEach((page, pageIndex) => {
      lines.push('', `### ${chapterIndex + 1}.${pageIndex + 1} ${page.title}`);
      if (page.bullets && page.bullets.length > 0) {
        page.bullets.forEach((bullet) => {
          lines.push(`- ${bullet}`);
        });
      } else {
        lines.push('- （暂无要点）');
      }
    });
  });

  return lines.join('\n');
}

export function exportOutlineMarkdown(outline: OutlineResult, fileName?: string) {
  const base = sanitizeFileName(fileName || outline.title || 'outline');
  const blob = new Blob([buildOutlineMarkdown(outline)], {
    type: 'text/markdown;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${base}.md`;
  link.click();
  URL.revokeObjectURL(url);
}
