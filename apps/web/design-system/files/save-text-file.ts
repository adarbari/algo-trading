/**
 * Save text the browser built as a file the user downloads (a Blob behind a temporary link).
 * Lives in the design system because it creates a DOM element (ADR 0025 rule 3).
 */
export function saveTextFile(name: string, text: string, type = 'text/csv;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(url); // after the browser has started the download
  }, 0);
}
