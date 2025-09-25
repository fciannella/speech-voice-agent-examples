// SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD 2-Clause License

export const RTC_CONFIG = {};
const { protocol, host } = window.location;
const wsProto = protocol === "https:" ? "wss" : "ws";

export const RTC_OFFER_URL = `${wsProto}://${host}/ws`;
export const POLL_PROMPT_URL = `/get_prompt`;
export const ASSISTANTS_URL = `/assistants`;

// Set to true to use dynamic prompt mode, false for default mode
export const DYNAMIC_PROMPT = false;
