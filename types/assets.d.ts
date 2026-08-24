declare module "*?url" {
  const url: string;
  export default url;
}

declare module "pdfmake/build/vfs_fonts.js" {
  const fonts: Record<string, string>;
  export default fonts;
}
