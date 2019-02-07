/*
  This code is based off the LUFA library and LoopBack demo code. Changes and additions
  to the original code are copyright 2013 Jonathan Thomson, jethomson.wordpress.com

  LUFA code is copyright 2009 Dean Camera (dean [at] fourwalledcubicle [dot] com)
  LoopBack demo code is copyright 2010-03-03 Opendous Inc.
    For more info visit: https://code.google.com/archive/p/micropendous/wikis/LoopBack.wiki

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


#ifndef _PULSEOX_USB_H_
#define _PULSEOX_USB_H_

	/* Includes: */
		#include <avr/io.h>
		#include <avr/wdt.h>
		#include <avr/interrupt.h>
		#include <avr/power.h>
		#include <string.h>

		#include "Descriptors.h"

		#include <LUFA/Version.h>
		#include <LUFA/Drivers/USB/USB.h>

		#include <inttypes.h>

	/* Function Prototypes: */
		void Main_Task(void);
		void Send_Data(void);

		void TSL230_Init(void);
		void Start_Timer(void);
		void Error_Halt(void);
	
		void EVENT_USB_Device_Connect(void);
		void EVENT_USB_Device_Disconnect(void);
		void EVENT_USB_Device_ConfigurationChanged(void);
		void EVENT_USB_Device_UnhandledControlRequest(void);

#endif
