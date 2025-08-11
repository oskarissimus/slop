import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import ffmpegStatic from 'ffmpeg-static';
import ffprobeStatic from 'ffprobe-static';
import ffmpeg from 'fluent-ffmpeg';
import { google } from 'googleapis';
import { v4 as uuidv4 } from 'uuid';
import OpenAI from 'openai';

// Configuration helper
function getConfig() {
  const env = process.env;
  const cfg = {
    openaiApiKey: env.OPENAI_API_KEY,
    elevenLabsApiKey: env.ELEVENLABS_API_KEY,
    youtubeClientId: env.YOUTUBE_CLIENT_ID,
    youtubeClientSecret: env.YOUTUBE_CLIENT_SECRET,
    youtubeRefreshToken: env.YOUTUBE_REFRESH_TOKEN,
    youtubeRedirectUri: env.YOUTUBE_REDIRECT_URI || 'http://localhost',
    voiceId: env.VOICE_ID || '21m00Tcm4TlvDq8ikWAM',
    personality: env.PERSONALITY_PROMPT || 'You are an insightful, optimistic, and curious narrator who presents concise, engaging facts and narratives with a warm, friendly tone.',
    cronSecret: env.CRON_SECRET || '',
    imageModel: env.IMAGE_MODEL || 'gpt-image-1',
    videoPrivacyStatus: env.VIDEO_PRIVACY_STATUS || 'public',
    topicTags: (env.TOPIC_TAGS || 'ai,technology,facts').split(',').map(t => t.trim()).filter(Boolean),
    numImages: Number(env.NUM_IMAGES || 8),
    targetSeconds: Number(env.TARGET_SECONDS || 120)
  };
  const missing = Object.entries({
    OPENAI_API_KEY: cfg.openaiApiKey,
    ELEVENLABS_API_KEY: cfg.elevenLabsApiKey,
    YOUTUBE_CLIENT_ID: cfg.youtubeClientId,
    YOUTUBE_CLIENT_SECRET: cfg.youtubeClientSecret,
    YOUTUBE_REFRESH_TOKEN: cfg.youtubeRefreshToken
  }).filter(([k, v]) => !v);
  if (missing.length) {
    throw new Error(`Missing required environment variables: ${missing.map(([k]) => k).join(', ')}`);
  }
  return cfg;
}

function ensureFfmpeg() {
  ffmpeg.setFfmpegPath(ffmpegStatic);
  ffmpeg.setFfprobePath(ffprobeStatic.path);
}

async function generateTopicAndScript(openai, personality, targetSeconds) {
  const topicSystem = `${personality}\nCreate timely, compelling topics that lead to a ~${Math.round(targetSeconds/60)} minute narrated video.`;
  const topicRes = await openai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: topicSystem },
      { role: 'user', content: 'Propose one fresh, clickable video topic with a short title and a one-sentence angle. Return JSON with keys: title, angle.' }
    ],
    temperature: 0.8,
    response_format: { type: 'json_object' }
  });
  let topicJson;
  try { topicJson = JSON.parse(topicRes.choices[0].message.content); } catch { topicJson = { title: 'Intriguing Insights', angle: 'A concise exploration.' }; }

  const targetWords = Math.round(140 * (targetSeconds / 60));
  const scriptSystem = `${personality}\nWrite a voiceover script around ${targetWords} words, vivid but concise, no scene directions, no timestamps.`;
  const scriptRes = await openai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: scriptSystem },
      { role: 'user', content: `Title: ${topicJson.title}\nAngle: ${topicJson.angle}\nWrite the full narration as paragraphs.` }
    ],
    temperature: 0.8
  });

  const script = scriptRes.choices[0].message.content.trim();
  return { topic: topicJson, script };
}

function splitScriptIntoPrompts(script, numImages) {
  const paragraphs = script.split(/\n\n+/).map(p => p.trim()).filter(Boolean);
  if (paragraphs.length === 0) {
    return new Array(numImages).fill('Abstract, cinematic background matching the narration.');
  }
  const prompts = [];
  for (let i = 0; i < numImages; i++) {
    const para = paragraphs[Math.floor((i / numImages) * paragraphs.length)] || paragraphs[paragraphs.length - 1];
    prompts.push(`${para} -- cinematic, cohesive style, detailed, high-resolution, vibrant, subtle motion feel.`);
  }
  return prompts;
}

async function generateImages(openai, prompts, model) {
  const outPaths = [];
  for (let i = 0; i < prompts.length; i++) {
    const prompt = prompts[i];
    const img = await openai.images.generate({
      model,
      prompt,
      size: '1024x1024'
    });
    const b64 = img.data[0].b64_json;
    const buf = Buffer.from(b64, 'base64');
    const filePath = path.join(os.tmpdir(), `img_${i + 1}.png`);
    fs.writeFileSync(filePath, buf);
    outPaths.push(filePath);
  }
  return outPaths;
}

async function synthesizeVoiceWithElevenLabs(text, voiceId, apiKey) {
  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'xi-api-key': apiKey,
      'Content-Type': 'application/json',
      'Accept': 'audio/mpeg'
    },
    body: JSON.stringify({
      text,
      model_id: 'eleven_multilingual_v2',
      voice_settings: { stability: 0.5, similarity_boost: 0.75 }
    })
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`ElevenLabs TTS failed: ${response.status} ${errText}`);
  }
  const arrayBuf = await response.arrayBuffer();
  const audioPath = path.join(os.tmpdir(), `voice_${uuidv4()}.mp3`);
  fs.writeFileSync(audioPath, Buffer.from(arrayBuf));
  return audioPath;
}

function ffprobeDuration(filePath) {
  return new Promise((resolve, reject) => {
    ffmpeg.ffprobe(filePath, (err, metadata) => {
      if (err) return reject(err);
      const stream = metadata.format;
      resolve(Number(stream.duration));
    });
  });
}

async function buildSlideshowVideo(imagePaths, audioPath, outputPath) {
  ensureFfmpeg();
  const audioDuration = await ffprobeDuration(audioPath);
  const perImage = audioDuration / imagePaths.length;

  const listPath = path.join(os.tmpdir(), `frames_${uuidv4()}.txt`);
  const lines = [];
  imagePaths.forEach((p, idx) => {
    lines.push(`file '${p.replace(/'/g, "'\\''")}'`);
    // Use exact duration for all but last; concat demuxer ignores duration on last entry
    if (idx < imagePaths.length - 1) {
      lines.push(`duration ${perImage}`);
    }
  });
  fs.writeFileSync(listPath, lines.join('\n'));

  const tempVideo = path.join(os.tmpdir(), `video_${uuidv4()}.mp4`);

  await runFfmpeg([
    '-f', 'concat', '-safe', '0', '-i', listPath,
    '-vsync', 'vfr', '-r', '30',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    tempVideo
  ]);

  await runFfmpeg([
    '-i', tempVideo, '-i', audioPath,
    '-c:v', 'copy', '-c:a', 'aac', '-shortest',
    outputPath
  ]);

  // cleanup temp video and list
  try { fs.unlinkSync(tempVideo); } catch {}
  try { fs.unlinkSync(listPath); } catch {}
}

function runFfmpeg(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(ffmpegStatic, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    proc.stderr.on('data', d => { stderr += d.toString(); });
    proc.on('error', reject);
    proc.on('close', code => {
      if (code === 0) resolve(undefined);
      else reject(new Error(`ffmpeg failed (${code}): ${stderr}`));
    });
  });
}

async function uploadToYouTube(videoPath, title, description, tags, privacyStatus, oauth) {
  const youtube = google.youtube('v3');
  const fileSize = fs.statSync(videoPath).size;
  const res = await youtube.videos.insert({
    part: ['snippet', 'status'],
    requestBody: {
      snippet: { title, description, tags },
      status: { privacyStatus }
    },
    media: {
      body: fs.createReadStream(videoPath)
    }
  }, {
    // For uploads, set maxContentLength and maxBodyLength if necessary
    maxContentLength: Infinity,
    maxBodyLength: Infinity
  });
  return res.data;
}

function initYouTubeOAuth(clientId, clientSecret, redirectUri, refreshToken) {
  const oauth2Client = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
  oauth2Client.setCredentials({ refresh_token: refreshToken });
  google.options({ auth: oauth2Client });
  return oauth2Client;
}

export const generateVideo = async (req, res) => {
  try {
    const cfg = getConfig();

    // Optional simple auth for scheduler
    if (cfg.cronSecret) {
      const headerSecret = req.get('x-cron-secret');
      if (headerSecret !== cfg.cronSecret) {
        res.status(401).send('Unauthorized');
        return;
      }
    }

    const openai = new OpenAI({ apiKey: cfg.openaiApiKey });
    const { topic, script } = await generateTopicAndScript(openai, cfg.personality, cfg.targetSeconds);

    const prompts = splitScriptIntoPrompts(script, cfg.numImages);
    const imagePaths = await generateImages(openai, prompts, cfg.imageModel);

    const audioPath = await synthesizeVoiceWithElevenLabs(script, cfg.voiceId, cfg.elevenLabsApiKey);

    const outputPath = path.join(os.tmpdir(), `final_${uuidv4()}.mp4`);
    await buildSlideshowVideo(imagePaths, audioPath, outputPath);

    const oauth = initYouTubeOAuth(cfg.youtubeClientId, cfg.youtubeClientSecret, cfg.youtubeRedirectUri, cfg.youtubeRefreshToken);

    const title = topic.title || 'AI Video';
    const description = `${topic.angle || ''}\n\nGenerated with AI narration by ElevenLabs.`.trim();
    const tags = cfg.topicTags;
    const result = await uploadToYouTube(outputPath, title, description, tags, cfg.videoPrivacyStatus, oauth);

    // Cleanup generated image and audio files
    imagePaths.forEach(p => { try { fs.unlinkSync(p); } catch {} });
    try { fs.unlinkSync(audioPath); } catch {}
    try { fs.unlinkSync(outputPath); } catch {}

    res.status(200).json({ status: 'ok', videoId: result.id, title });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: String(err && err.message ? err.message : err) });
  }
};