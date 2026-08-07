# LightWeave submission checklist

Last reviewed: 2026-08-06

This is an evidence-based audit of the repository against the provided
hackathon requirements. A checked source item means the repository contains
the required material; it does not replace the two owner-only form submissions.

## Required items

| Requirement | Status | Repository evidence or action |
| --- | --- | --- |
| All code is open source | Pass | Source for Windows, Android, UNO Q/App Lab, protocol, installers, and tests is tracked. Generated/vendor artifacts stay out of Git. |
| Every team member submitted feedback | Owner action | This cannot be established from source control. Confirm every member has submitted the feedback form. |
| Personal GitHub repository | Pass | <https://github.com/WickedStereo/LightWeave> |
| README application description | Pass | The README describes text/image/audio encoding, USB handoff, optical framing, and Qualcomm reconstruction paths. |
| README team names and emails | **Blocked** | Exact public roster and preferred email addresses are not available locally. Replace the temporary Team note before submission. |
| Setup from scratch and dependencies | Pass | `scripts/setup_windows.ps1`, `docs/SETUP_WINDOWS.md`, target-specific READMEs, and hash-checking UNO Q installers are tracked. |
| Run and usage instructions | Pass | The README documents CLI/dashboard use, App Lab installation, transmission, reception, and verification commands. |
| Open-source license | Pass | Root `LICENSE` is MIT; third-party notices and SBOMs are tracked for the board bundle. |
| Runnable on intended Copilot+ PC | Pass with documented prerequisites | Exercised on Snapdragon X Elite/Windows 11 ARM64 with separate x64 codec and ARM64 QNN environments. Strict QNN evidence is recorded in the README and living engineering log. |
| Functions as described | Pass for verified scope | Text, three image profiles, and one-second audio crossed the two-board optical link. Five-second audio decoding is supported but its intentionally long physical transfer was not run. |
| Deployable/downloadable maturity | Pass for open-source release | The public GitHub repository is a downloadable, reproducibly source-installable distribution with offline installers, validation, failure handling, tests, and licenses. It is not a signed app-store package and does not claim commercial certification, authentication, or production clock recovery. |
| GitHub link submitted by 12pm August 7 | Owner action | Submit the repository URL through the supplied Microsoft Form before the stated deadline. |

## Recommended items

| Recommendation | Status | Evidence |
| --- | --- | --- |
| Tests and testing instructions | Pass | `tests/`, GitHub Actions, README acceptance commands, Android tests, and board verification scripts. |
| Notes beyond the description | Pass | `PROJECT_CONTEXT.md`, Qualcomm developer-experience log, protocol notes, and target READMEs. |
| References | Pass | README/context references include Qualcomm documentation, model projects, ncnn, EnCodec, and Arduino resources. |
| Well-commented code | Pass with normal maintenance | Critical protocol, accelerator, installer, and failure-boundary code is documented; comments are used where behavior is not self-evident. |

## Final owner actions

1. Replace the README Team note with every member's exact public name and email.
2. Confirm that every listed member submitted the feedback form.
3. Run the clean-machine setup and repository test commands one final time.
4. Confirm the public GitHub repository contains the intended commits and no
   private hackathon material, tokens, generated weights, or device data.
5. Submit <https://github.com/WickedStereo/LightWeave> through the Microsoft
   Form before 12pm August 7.

## Release wording

The defensible release description is: **an open-source, reproducibly
installable hackathon application verified on Snapdragon X Elite and Arduino
UNO Q hardware**. Do not claim measured energy consumption, general optical
reliability, a fully NPU-backed audio decoder, or commercial certification.
