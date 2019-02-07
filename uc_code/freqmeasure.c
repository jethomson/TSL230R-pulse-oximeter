/*
  Copyright 2013 Jonathan Thomson, jethomson.wordpress.com

  This code uses capture.h from Paul Stoffregen's FreqMeasure library.
  https://www.pjrc.com/teensy/td_libs_FreqMeasure.html

  Permission to use, copy, modify, and distribute this software
  and its documentation for any purpose and without fee is hereby
  granted, provided that the above copyright notice appear in all
  copies and that both that the copyright notice and this
  permission notice and warranty disclaimer appear in supporting
  documentation, and that the name of the author not be used in
  advertising or publicity pertaining to distribution of the
  software without specific, written prior permission.

  The author disclaim all warranties with regard to this
  software, including all implied warranties of merchantability
  and fitness.  In no event shall the author be liable for any
  special, indirect or consequential damages or any damages
  whatsoever resulting from loss of use, data or profits, whether
  in an action of contract, negligence or other tortious action,
  arising out of or in connection with the use or performance of
  this software.
*/

#include <avr/pgmspace.h>
#include "freqmeasure.h"
#include "fLUT.h"
#include "capture.h"

static uint8_t sample_ready;
static uint8_t num_captures;
static uint32_t capture_t0;
static uint32_t capture;
static uint32_t freq;

uint8_t freqmeasure_available(void)
{
	return sample_ready;
}

uint32_t freqmeasure_read(void)
{
	sample_ready = 0;
	return freq;
}

void freqmeasure_begin(void)
{
	sample_ready = 0;
	num_captures = 0;
	capture_t0 = 0;
	capture = 0;
	freq = 0;
	capture_init();
	capture_start();
}

void freqmeasure_end(void)
{
	capture_shutdown();
}

ISR(TIMER_CAPTURE_VECTOR)
{
	uint16_t period;

	capture_t0 = capture;
	capture = capture_read();
	num_captures++;
	// better results are obtained by ignoring the first two captures
	if (num_captures == 4)
	{
		// The x's between the i's and t's indicate the portion of
		// the pulse that is missed.
		// t--ixxt-----t-----txi---t-----
		// On average when these portions are added together they equal
		// 1 tick. Add 1 to account for these portions.
		period = (capture - capture_t0) + 1;
		if (period < fLUT_size && !capture_overflow())
		{
			freq = pgm_read_dword_near(fLUT + period);
		}
		else
		{
			freq = 0;
			DDRC |= _BV(PC2);
			PORTC |= _BV(PC2); // error LED on
		}
		freqmeasure_end();
		sample_ready = 1;
	}
	
}
