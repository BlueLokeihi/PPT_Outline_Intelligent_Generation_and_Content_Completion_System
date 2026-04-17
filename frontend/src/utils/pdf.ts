import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfExtractionResult {
  pageCount: number;
  text: string;
}

export async function extractPdfText(file: File): Promise<PdfExtractionResult> {
  const data = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({ data });
  const doc = await loadingTask.promise;

  const pageTexts: string[] = [];
  for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber += 1) {
    const page = await doc.getPage(pageNumber);
    const content = await page.getTextContent();
    const line = content.items
      .map((item) => ('str' in item ? item.str.trim() : ''))
      .filter(Boolean)
      .join(' ');
    pageTexts.push(`[Page ${pageNumber}] ${line}`);
  }

  return {
    pageCount: doc.numPages,
    text: pageTexts.join('\n\n').trim(),
  };
}
