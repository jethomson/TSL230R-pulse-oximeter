/*
  This code is based off the LUFA library and LoopBack demo code. Changes and additions
  to the original code are copyright 2013 Jonathan Thomson, jethomson.wordpress.com

  LUFA code is copyright 2009 Dean Camera (dean [at] fourwalledcubicle [dot] com)
  LoopBack demo code is copyright 2010-03-03 Opendous Inc.
    For more info visit: https://code.google.com/archive/p/micropendous/wikis/LoopBack.wiki

  This firmware enumerates as a vendor-class device meaning
  the developer must decide and code a communication scheme.
  Examples of arbitrary endpoint as well as control endpoint
  communication are given.
  Search for TODO statements for implementation hints.
  Avoid busy loops as the USB task is not preemptive and USB
  has timing contraints.  Use concurrent programming techniques.
  For example, have one function set a flag when an event occurs.
  Have another function do significant processing only if the flag is set.
  Have both functions run from main()'s for(;;) loop, which should be the
  only indefinite loop in your firmware.

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

/* Global Variables */
/* EP_SIZE is defined in Descriptors.h and should be
 * less than or equal to 64 bytes in order to work with Control Endpoint data.
 */

/*
   Rainbow Ribbon Cable
   Orange 1.  S0 = PD5
   Yellow 2.  S1 = PD6   //  green LED
   Green  3. nOE = PD7   // HWB button
   Blue   4. GND
   Purple 5. VCC
   Gray   6. OUT = PC7  on ATmega32U2 FreqMeasure uses Timer1 ICP
   White  7.  S2 = PB3
   Black  8.  S3 = PB2

   red_LED_pin = PD0 & PD1, measured: 150||150 = 75 ohm, 23.30 mA
   IR_LED_pin = PD2, measured: 217.2 ohm, 15.38 mA, 4.53 V
*/

/*
   Every sample period a new sample is taken from the TSL230 for both
   the red and IR LEDs, both samples are placed in moving average buffers
   of size M, and the moving average is calculated. The period between samples
   is (OCR0A*clk_div)/clk
   The moving average results for each LED and their sample number make up
   what's called a dataset. Every Nth sample a dataset is buffered for output.
   So the buffer gets a new dataset at a rate of
   clk/(N*OCR0A*clk_div) where N is NTH_SAMPLE.
   A dataset is three 32 bit numbers which is 12 bytes. The output buffer has
   to be 64 bytes or less so a max of five datasets can be buffered.
   To ensure that the buffer always has fresh data the host program should not
   read data faster than clk/(5*N*OCR0A*clk_div)

   With clk=16000000, N=5, OCR0A=250, and clk_div=64, then
   in the python program should have:
   FSAMPLE = 40 # [Hz] 16000000/(5*5*250*64)
   UC_TIMER_PERIOD = 0.001 # [s] (250*64)/16000000
*/

#include "pulseox_USB.h"
#include "freqmeasure.h"
#define USB_BUFSIZE   5*3  // 3 data points per dataset. buffer 5 datasets.
//#define M   64  // number of samples to average, works well at home
#define M   128  // number of samples to average, better at apt?
#define NTH_SAMPLE   6   // buffer a dataset to be output every Nth sample

#define RED_ON          PORTD |= _BV(PD0) | _BV(PD1)
#define RED_OFF         PORTD &= ~(_BV(PD0) | _BV(PD1))
#define IR_ON           PORTD |= _BV(PD2)
#define IR_OFF          PORTD &= ~_BV(PD2)
#define ERR_LED_ON      PORTC |= _BV(PC2)
#define ERR_LED_OFF     PORTC &= ~_BV(PC2)
#define ERR_LED_TOGL    PORTC ^= _BV(PC2)

#define LOG2F(x)    ( (((x) >= 2)    ? 1 : 0) + \
       	              (((x) >= 4)    ? 1 : 0) + \
       	              (((x) >= 8)    ? 1 : 0) + \
       	              (((x) >= 16)   ? 1 : 0) + \
       	              (((x) >= 32)   ? 1 : 0) + \
       	              (((x) >= 64)   ? 1 : 0) + \
       	              (((x) >= 128)  ? 1 : 0) + \
       	              (((x) >= 256)  ? 1 : 0) + \
       	              (((x) >= 512)  ? 1 : 0) + \
       	              (((x) >= 1024) ? 1 : 0) )

static uint32_t dataToSend[USB_BUFSIZE] = {0};
volatile static uint8_t take_sample = 1;
static uint8_t idx = 0;
static uint8_t new_dataset_buffered = 0;

ISR(TIMER0_COMPA_vect)
{
	//PORTD ^= _BV(PD3); // DEBUG: toggle to oscilloscope
	take_sample = 1;
}

int main(void)
{
	cli();

	/* Disable watchdog if enabled by bootloader/fuses */
	MCUSR &= ~(1 << WDRF);
	wdt_disable();

	/* Disable clock division */
	clock_prescale_set(clock_div_1);

	//configure red LED port and turn off
	DDRD |= _BV(PD0) | _BV(PD1);
	RED_OFF;

	//configure IR LED port and turn off
	DDRD |= _BV(PD2);
	IR_OFF;

	// configure error LED port
	DDRC |= _BV(PC2);
	ERR_LED_OFF;

	// DEBUG
	// configure oscilloscope port
	DDRD |= _BV(PD3);

	TSL230_Init();
	USB_Init();
	Start_Timer();
	sei();

	for (;;)
	{
		Main_Task();
		USB_USBTask();
	}

}

/** Main_Task will only Send if USB is connected */
void Main_Task(void)
{
	static uint16_t buff_red[M] = {0};
	static uint16_t buff_ir[M] = {0};
	static uint32_t sum_red = 0;
	static uint32_t sum_ir = 0;
	static uint16_t i = 0;
	static uint8_t j = 0;
	static uint32_t sample_num = 0;

	if (take_sample)
	{
		take_sample = 0;

		RED_ON;
		freqmeasure_begin();
		while (!freqmeasure_available())
			continue;
		RED_OFF;
		sum_red = sum_red - buff_red[i];
		buff_red[i] = freqmeasure_read();
		sum_red = sum_red + buff_red[i];

		IR_ON;
		freqmeasure_begin();
		while (!freqmeasure_available())
			continue;
		IR_OFF;
		sum_ir = sum_ir - buff_ir[i];
		buff_ir[i] = freqmeasure_read();
		sum_ir = sum_ir + buff_ir[i];

		i++;
		if (i == M)
			i = 0;

		j++;
		if (j == NTH_SAMPLE)
		{
			j = 0;

			dataToSend[idx] = ((sum_red+_BV((LOG2F(M)-1))) >> LOG2F(M));
			dataToSend[idx+1] = ((sum_ir+_BV((LOG2F(M)-1))) >> LOG2F(M));
			dataToSend[idx+2] = sample_num;
			sample_num++;

			new_dataset_buffered = 1;

			idx = idx+3;
			if (idx == USB_BUFSIZE)
				idx = 0;
		}

	}

	if (USB_DeviceState == DEVICE_STATE_Configured && new_dataset_buffered == 1)
	{
		PORTD |= _BV(PD3); // DEBUG: high to oscilloscope
		Send_Data();
		PORTD &= ~_BV(PD3); // DEBUG: low to oscilloscope
	}

}

/** Sends data to the host via regular endpoints */
void Send_Data(void)
{
	uint8_t ErrorCode;

	/* Select the IN Endpoint */
	Endpoint_SelectEndpoint(IN_EP);

	if (Endpoint_IsConfigured() && Endpoint_IsINReady() && Endpoint_IsReadWriteAllowed())
	{
		/* Write data to the host from oldest to newest */
		ErrorCode = Endpoint_Write_Stream_LE(&dataToSend[idx], sizeof(uint32_t)*(USB_BUFSIZE-idx), NULL);
		ErrorCode = Endpoint_Write_Stream_LE(&dataToSend[0], sizeof(uint32_t)*idx, NULL);
		if (ErrorCode != ENDPOINT_RWSTREAM_NoError)
		{
			Error_Halt(); // this never returns
		}
		Endpoint_ClearIN();
		new_dataset_buffered = 0;
	}

}

void TSL230_Init(void)
{
	// disable TSL230
	DDRD |= _BV(PD7);
	PORTD |= _BV(PD7);

	//set sensitivity to 100x
	DDRD |= _BV(PD5);
	DDRD |= _BV(PD6);
	PORTD |= _BV(PD5); // S0 = 1
	PORTD |= _BV(PD6); // S1 = 1

	//set frequency scaling 1x
	DDRB |= _BV(PB3);
	DDRB |= _BV(PB2);
	PORTB &= ~_BV(PB3);
	PORTB &= ~_BV(PB2);

	// enable TSL230
	PORTD &= ~_BV(PD7);
}

void Start_Timer(void)
{
	TIMSK0 &= ~_BV(OCIE0A);  // disable timer compare interrupt
	TIFR0 = _BV(OCF0A);      // clear interrupt flag
	TCNT0 = 0;
	take_sample = 0;

	TCCR0A |= _BV(WGM01);    // CTC mode

	// The fastest the python program can take reading from the USB is
	// about 2 ms so it doesn't makes sense to sample any faster than that.
	// If num_captures == 4, sampling both LEDs takes max of 400 us
	OCR0A = 250; // 250 ticks @ 16 MHz, clk/64 = 1000 us

	TIMSK0 |= _BV(OCIE0A);  // enable timer compare interrupt
	TCCR0B |= _BV(CS01) | _BV(CS00);    // start timer, clk/64
}

void Error_Halt(void)
{
	// disable TSL230
	DDRD |= _BV(PD7);
	PORTD |= _BV(PD7);

	// power down TSL230
	DDRD |= _BV(PD5);
	DDRD |= _BV(PD6);
	PORTD &= ~_BV(PD5); // S0 = 0
	PORTD &= ~_BV(PD6); // S1 = 0

	while(1)
	{
		ERR_LED_ON;
		_delay_ms(1000);
		ERR_LED_OFF;
		_delay_ms(1000);
	}
}


/** Event handler for the USB_Connect event. This indicates that the device is enumerating via the status LEDs and
 *  starts the library USB task to begin the enumeration and USB management process.
 */
void EVENT_USB_Device_Connect(void)
{
	/* Indicate USB enumerating */
}

/** Event handler for the USB_Disconnect event. This indicates that the device is no longer connected to a host via
 *  the status LEDs.
 */
void EVENT_USB_Device_Disconnect(void)
{
	/* Indicate USB not ready */
}

/** Event handler for the USB_ConfigurationChanged event. This is fired when the host sets the current configuration
 *  of the USB device after enumeration, and configures the device endpoints.
 */
void EVENT_USB_Device_ConfigurationChanged(void)
{
	uint8_t i = 0;
	bool success = 1;

	/* Setup SendDataToHost Endpoint */
	success &= Endpoint_ConfigureEndpoint(IN_EP, EP_TYPE_BULK,
	                                      ENDPOINT_DIR_IN, EP_SIZE,
	                                      ENDPOINT_BANK_SINGLE);

	while (!success)
	{
		ERR_LED_ON;
		_delay_ms(1000);
		ERR_LED_OFF;
		_delay_ms(1000);
	}

	for (i = 0; i < 5; i ++)
	{
		ERR_LED_ON;
		_delay_ms(50);
		ERR_LED_OFF;
		_delay_ms(50);
	}
}

/** Event handler for the USB_UnhandledControlRequest event. This is used to catch standard, class,
 *  and vendor specific control requests that are not handled internally by the USB library so that
 *  they can be handled appropriately for the application.
 */
void EVENT_USB_Device_UnhandledControlRequest(void)
{
	/* Process specific control requests */
	switch (USB_ControlRequest.bRequest)
	{
		default: break;
	}
}

