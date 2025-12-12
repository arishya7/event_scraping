import { GoogleGenAI } from "@google/genai";
import type { ScrapeResult, Source } from '../types';


const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

export const scrapeUrl = async (url: string): Promise<ScrapeResult> => {
  try {
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: "Please act as an expert web scraper and content analyst.
      Analyze the main textual content of the website at the following URL.
      Provide a concise, well-structured summary of its key information, purpose, and main points.
      Ignore ads, navigation menus, and footers. Focus on the core content.
      URL: ${url}",
      config: {
        tools: [{ googleSearch: {} }],
      },
    });
    
    const summary = response.text;
    if (!summary) {
        throw new Error("The AI did not return a summary.");
    }

    const groundingChunks = response.candidates?.[0]?.groundingMetadata?.groundingChunks;

    const sources: Source[] = groundingChunks?.map((chunk: any) => ({
      uri: chunk.web?.uri || '#',
      title: chunk.web?.title || 'Unknown Source'
    })).filter((source: Source, index: number, self: Source[]) => 
        index === self.findIndex((s) => s.uri === source.uri)
    ) || [];

    return { summary, sources };

  } catch (error) {
    console.error("Error calling Gemini API:", error);
    throw new Error("Failed to communicate with the Gemini API.");
  }
};
