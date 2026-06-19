**I'm leaving the original Readme unchanged below my adaptations, to link back to the original creator - give him some love!**

## Change 1: tuning of 1.4k
TLDR; My change is extremely simple - exchange R34 from 15k to 18k.

### Explanation for adaptation
I noticed, that when tuning the 1.4k band I could not get the gain down to 6.5dB - the lowest position of Q trimmer achieved something akin to 6.7dB. I scratched my head for about a week searching for errors in my build, when I decided to simulate each band in LTSpice. Lo and behold - the 1.4k band with Q trimmer set to 1 Ohm and frequency pot trimmed so that the peak is at exactly 1.4k gave around 6.7dB - as measured. It all stems from the fact, that the Q and freq trimmers are interacting with each other quite heavily.
Next step was preparing a tool to help finding the correct value - Copilot came to the rescue and gave me a Python script that is capable of just that. I'll leave it in the repository as well in Simulator directory. I searched for a minimal change of components, that could give me at most 6dB, preferrably 5.5dB, of gain at minimum Q position, with center frequency tuned to 1.4k. It turns out, that just bumping the R34 resistor from 15k to 18k does the trick nicely.
I replaced the resistor, calibrated the module once more and all was well :)

## Change 2: Frontpanel
I prepared a frontpanel using EasyEDA. It's similar to the one shown on the MMI Modular pictures. Gerber files can be found in Frontpanel directory.

# Original README

**If you would like to build this project yourself, PCBs can be purchased through [Pusherman](https://pushermanproductions.com/product/mmi-modular-two-nine-five-buchla-comb-filter-pcb-14hp-black-gold-aluminium-panel/) or [Modular Addict](https://modularaddict.com/mmi-259-pcbpanel)**

**If you would like to purchase a pre-built unit, keep an eye on my [Reverb shop](https://reverb.com/shop/mmi-modular)**

# Two Nine Five

* Eurorack adaptation of the Buchla Model 295 10-channel comb filter
* 10 LED sliders control the amplitude of each band sent through the SUM output
* Individual channel outputs to the right of each slider
* Tunable band frequencies, Q's, and amplitude via trim pots on the back of the module.

This recreation of the Model 295 has been in my head since before I owned any modular. After using a restored Buchla at the Oberlin Conservatory of Music, the 295 became one of my favorite modules in the whole case. Buchla modular is far out of my budget so with the original schematics in hand, I made a much more compact 3U version of it. The circuitry is exactly the same, though more modern op-amps have to be used since the ones used in the original design are no longer available.

---

**Things to note when building**

It is absolutely imperative that you solder R13, R39, R17, R37, R19, R35, R25, and R33 properly before mounting the trim pots as they will be very difficult to reach once all components are in place. To confirm they are soldered properly, measure the resistance between the two middle pins of each trim pot location. For instance, the resistance between the middle pin of VR10 and VR9 should be roughly 68 kOhms.

In addition, please heed the warning on the front of the PCB and place the trim pots on the back of the module. There is not enough space between the PCB and panel for the trim pots and having them on the back allows for you to tune everything without taking the panel off. I kept the silk screen for the pots on the top side in order to avoid cluttering the bottom silkscreen layer.

As for the illuminated slide pots, there's a few things to consider. They are acting as cross faders so any value between 10k and 100k should work just fine. They are taking an audio signal so ideally you want audio response, but linear response will function just fine. Ideal shaft length is 15mm but I have used 10mm successfully, the tops are just a tad close to the panel. You do not want a center detent if you can help it. The sliders I used can be found on Mouser: 652-PTL20-10R0-103B2

---

**How to tune your 295**

Note: You may want to keep the volume down for this or else you might give yourself a headache.

*Tuning Frequency*

* Turn each 20k trim pot so that every band has maximum gain (some bands will self-oscillate, others will not)
* Patch white noise to **IN** and monitor **SUM** with a FFT-capable spectrum analyzer or parametric/graphic EQ
* Slide the potentiometer of the band you want to tune all the way to the right
* Turn the appropriate 100k trim pot until the peak is centered on the desired frequency
* Repeat for each band

*Tuning Gain/Q*

* Using a sine wave oscillator, patch the wave directly to your output 
* Set the gain between your modular and a VU meter (usually within a DAW) so that the output is now at 0dB
* Leaving the output gain unchanged, move the sine wave to an attenuator and attenuate it down to -6.5dB
* Patch this attenuated sine wave to **IN** then patch **SUM** to your output
* Slide the potentiometer of the band you want to tune all the way to the right
* Tune your sine wave to match the frequency of the band you would like to tune
* Turn the appropriate 20k trim pot until your output is at 0dB
* Repeat for each band

It may help to monitor your output with an oscilloscope to see how your output clips. Note that each band clips asymmetrically. This can cause some interesting harmonics to show up so feel free to tune your filter to taste, no need to follow this guide to a T.

---

PCB and panel designed by me

Original schematic by Don Buchla

![Imgur](https://i.imgur.com/43DXM32.jpg)

![Imgur](https://i.imgur.com/BFru6uz.jpg)
